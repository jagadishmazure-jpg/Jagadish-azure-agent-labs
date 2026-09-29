// legal-document-compliance: contract and policy compliance extraction. Compile-checked only; never deployed from this repo.
// Keys and local auth are disabled everywhere; workloads authenticate with a user-assigned managed identity.
targetScope = 'resourceGroup'

@description('Short prefix for resource names')
@maxLength(10)
param prefix string = 'legal'
param location string = resourceGroup().location
@allowed(['us', 'eu'])
@description('Data zone for Foundry model deployments (DataZoneStandard keeps processing in-zone)')
param dataZone string = 'us'
param classifierModel string = 'gpt-5-mini'
param modelVersion string = '2025-08-07'

var suffix = uniqueString(resourceGroup().id)
var tags = { lab: 'legal-document-compliance', deployed: 'never-from-this-repo' }

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${prefix}-id-${suffix}'
  location: location
  tags: tags
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${prefix}-log-${suffix}'
  location: location
  tags: tags
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${prefix}-appi-${suffix}'
  location: location
  kind: 'web'
  tags: tags
  properties: { Application_Type: 'web', WorkspaceResourceId: logs.id, DisableLocalAuth: true }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: take('${prefix}st${suffix}', 24)
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    isHnsEnabled: true
    allowSharedKeyAccess: false
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: '${prefix}-srch-${suffix}'
  location: location
  tags: tags
  sku: { name: 'basic' }
  properties: { disableLocalAuth: true, replicaCount: 1, partitionCount: 1, publicNetworkAccess: 'enabled' }
}

resource foundry 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: '${prefix}-ai-${suffix}'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  properties: { customSubDomainName: '${prefix}-ai-${suffix}', disableLocalAuth: true, publicNetworkAccess: 'Enabled' }
}

resource classifierDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundry
  name: 'clause-classifier'
  sku: { name: 'DataZoneStandard', capacity: 10 }
  properties: { model: { format: 'OpenAI', name: classifierModel, version: modelVersion } }
}

resource docIntel 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: '${prefix}-di-${suffix}'
  location: location
  tags: tags
  kind: 'FormRecognizer'
  sku: { name: 'S0' }
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  properties: { customSubDomainName: '${prefix}-di-${suffix}', disableLocalAuth: true, publicNetworkAccess: 'Enabled' }
}

resource cae 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${prefix}-cae-${suffix}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: { customerId: logs.properties.customerId, sharedKey: logs.listKeys().primarySharedKey }
    }
  }
}

output dataZone string = dataZone
output identityClientId string = identity.properties.clientId
output foundryEndpoint string = foundry.properties.endpoint
output docIntelEndpoint string = docIntel.properties.endpoint
