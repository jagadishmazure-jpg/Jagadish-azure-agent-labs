// disaster-signal-fusion: what this lab would need in Azure. Compile-checked only; never deployed.
// Every data service disables local (key) auth; the workload identity is a user-assigned managed identity.
targetScope = 'resourceGroup'

@description('Short prefix for resource names')
@maxLength(10)
param prefix string = 'dsf'
param location string = resourceGroup().location
@allowed(['us', 'eu'])
@description('Data zone for the Foundry model deployment (DataZoneStandard keeps processing in-zone)')
param dataZone string = 'us'
param summaryModel string = 'gpt-5-mini'
param summaryModelVersion string = '2025-08-07'

var suffix = uniqueString(resourceGroup().id)
var tags = { lab: 'disaster-signal-fusion', deployed: 'never-from-this-repo' }

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

resource eventHubs 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: '${prefix}-evh-${suffix}'
  location: location
  tags: tags
  sku: { name: 'Standard', tier: 'Standard', capacity: 1 }
  properties: { disableLocalAuth: true, minimumTlsVersion: '1.2' }
}

resource signalsHub 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: eventHubs
  name: 'sensor-signals'
  properties: { partitionCount: 4, messageRetentionInDays: 1 }
}

resource fusionGroup 'Microsoft.EventHub/namespaces/eventhubs/consumergroups@2024-01-01' = {
  parent: signalsHub
  name: 'fusion-desk'
}

resource lake 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: take('${prefix}lake${suffix}', 24)
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    isHnsEnabled: true // ADLS Gen2: raw / curated / deadletter zones
    allowSharedKeyAccess: false
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${prefix}-plan-${suffix}'
  location: location
  tags: tags
  sku: { name: 'Y1', tier: 'Dynamic' }
  kind: 'functionapp'
  properties: { reserved: true }
}

resource featureFunctions 'Microsoft.Web/sites@2023-12-01' = {
  name: '${prefix}-func-${suffix}'
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'Python|3.12'
      appSettings: [
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        { name: 'AzureWebJobsStorage__accountName', value: lake.name }
        { name: 'AzureWebJobsStorage__credential', value: 'managedidentity' }
        { name: 'AzureWebJobsStorage__clientId', value: identity.properties.clientId }
        { name: 'SIGNALS__fullyQualifiedNamespace', value: '${eventHubs.name}.servicebus.windows.net' }
        { name: 'SIGNALS__credential', value: 'managedidentity' }
        { name: 'SIGNALS__clientId', value: identity.properties.clientId }
        { name: 'APPLICATIONINSIGHTS_AUTHENTICATION_STRING', value: 'Authorization=AAD;ClientId=${identity.properties.clientId}' }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
      ]
    }
  }
}

resource maps 'Microsoft.Maps/accounts@2023-06-01' = {
  name: '${prefix}-maps-${suffix}'
  location: 'global'
  tags: tags
  sku: { name: 'G2' }
  kind: 'Gen2'
  properties: { disableLocalAuth: true }
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

resource summaryDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundry
  name: 'dsf-situation-summary'
  sku: { name: 'DataZoneStandard', capacity: 10 }
  properties: { model: { format: 'OpenAI', name: summaryModel, version: summaryModelVersion } }
}

output dataZone string = dataZone
output identityClientId string = identity.properties.clientId
output eventHubNamespace string = '${eventHubs.name}.servicebus.windows.net'
output lakeAccount string = lake.name
output foundryEndpoint string = foundry.properties.endpoint
