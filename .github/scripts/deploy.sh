#!/usr/bin/env bash
# Deployment steps for one lab, used by .github/workflows/deploy.yml and teardown.yml.
# Inputs (environment):
#   LAB           lab folder name under labs/
#   DEPLOY_TOOL   terraform | bicep
#   TARGET_ENV    dev | prod
#   LOCATION      Azure region (default eastus2)
#   ARM_* / AZURE_*  set by azure/login (OIDC) and the workflow env
#
#   deploy.sh provision   create/update the lab's resources, write outputs to $GITHUB_OUTPUT
#   deploy.sh smoke       post-deploy checks: resources exist, Foundry endpoint reachable, keyless
#   deploy.sh destroy     tear the lab environment down (teardown workflow only)
# The labs run offline against mocks; there is no container image to build or push.
set -euo pipefail

LAB="${LAB:?LAB is required}"
TOOL="${DEPLOY_TOOL:-terraform}"
ENV_NAME="${TARGET_ENV:?TARGET_ENV is required}"
LOCATION="${LOCATION:-eastus2}"
STACK="labs/${LAB}/infra/terraform"
OUT="${GITHUB_OUTPUT:-/dev/stdout}"

prefix() {
  case "$LAB" in
    disaster-signal-fusion) echo dsf ;; legal-document-compliance) echo legal ;;
    medical-eye-scan-multimodal) echo eye ;; road-network-maintenance-graph) echo road ;;
    wind-turbine-continual-learning) echo wtg ;; *) echo "unknown lab $LAB" >&2; exit 1 ;;
  esac
}
region_short() {
  case "$LOCATION" in
    eastus) echo eus ;; eastus2) echo eus2 ;; westus2) echo wus2 ;; westus3) echo wus3 ;;
    centralus) echo cus ;; swedencentral) echo sdc ;; westeurope) echo weu ;;
    northeurope) echo neu ;; uksouth) echo uks ;; *) echo "${LOCATION:0:6}" ;;
  esac
}
RG="rg-$(prefix)-${ENV_NAME}-$(region_short)-001"

tf_init() {
  : "${TFSTATE_RESOURCE_GROUP:?set repo/environment variable TFSTATE_RESOURCE_GROUP}"
  : "${TFSTATE_STORAGE_ACCOUNT:?set repo/environment variable TFSTATE_STORAGE_ACCOUNT}"
  terraform -chdir="$STACK" init -input=false \
    -backend-config="envs/${ENV_NAME}.backend.hcl" \
    -backend-config="resource_group_name=${TFSTATE_RESOURCE_GROUP}" \
    -backend-config="storage_account_name=${TFSTATE_STORAGE_ACCOUNT}" \
    -backend-config="container_name=${TFSTATE_CONTAINER:-tfstate}"
}

provision() {
  if [[ "$TOOL" == "terraform" ]]; then
    tf_init
    terraform -chdir="$STACK" apply -auto-approve -input=false \
      -var-file="envs/${ENV_NAME}.tfvars" -var "location=${LOCATION}"
    rg=$(terraform -chdir="$STACK" output -raw AZURE_RESOURCE_GROUP)
    endpoint=$(terraform -chdir="$STACK" output -raw foundryEndpoint)
  else
    az group create --name "$RG" --location "$LOCATION" \
      --tags env="$ENV_NAME" owner=jagadish.meduri project=azure-agent-labs cost-center=portfolio lab="$LAB" -o none
    outputs=$(az deployment group create --resource-group "$RG" --name "${LAB}-${GITHUB_RUN_ID:-local}" \
      --template-file "labs/${LAB}/infra/main.bicep" --parameters prefix="$(prefix)" \
      --query properties.outputs -o json)
    rg="$RG"
    endpoint=$(jq -r .foundryEndpoint.value <<<"$outputs")
  fi
  { echo "resource_group=$rg"; echo "foundry_endpoint=$endpoint"; } >>"$OUT"
}

smoke() {
  : "${RESOURCE_GROUP:?}" "${FOUNDRY_ENDPOINT:?}"
  n=$(az resource list -g "$RESOURCE_GROUP" --query "length(@)" -o tsv)
  [[ "$n" -ge 3 ]] || { echo "::error::expected lab resources in $RESOURCE_GROUP, found $n"; exit 1; }
  echo "$n resources in $RESOURCE_GROUP"
  # keyless check: the account must reject key auth; any HTTP answer proves DNS + TLS reachability
  code=$(curl -s -o /dev/null -w '%{http_code}' "${FOUNDRY_ENDPOINT%/}/openai/models?api-version=2024-10-21" || true)
  [[ "$code" =~ ^[0-9]{3}$ && "$code" != "000" ]] || { echo "::error::Foundry endpoint unreachable"; exit 1; }
  echo "Foundry endpoint reachable (HTTP $code without a token, as expected)"
  local_auth=$(az cognitiveservices account list -g "$RESOURCE_GROUP" --query "[?properties.disableLocalAuth!=\`true\`] | length(@)" -o tsv)
  [[ "$local_auth" == "0" ]] || { echo "::error::a Cognitive Services account allows key auth"; exit 1; }
}

destroy() {
  if [[ "$TOOL" == "terraform" ]]; then
    tf_init
    terraform -chdir="$STACK" destroy -auto-approve -input=false \
      -var-file="envs/${ENV_NAME}.tfvars" -var "location=${LOCATION}"
  else
    az group delete --name "$RG" --yes
  fi
}

"$@"
