// wind-turbine-continual-learning: SCADA anomaly detection with an eval-gated detector registry. Compile-checked only; never deployed from this repo.
// Keys and local auth are disabled everywhere; workloads authenticate with a user-assigned managed identity.
targetScope = 'resourceGroup'

@description('Short prefix for resource names')
@maxLength(10)
param prefix string = 'wtg'
param location string = resourceGroup().location
@allowed(['us', 'eu'])
@description('Data zone for Foundry model deployments (DataZoneStandard keeps processing in-zone)')
param dataZone string = 'us'
param diagnosisModel string = 'gpt-5-mini'
param modelVersion string = '2025-08-07'

@description('Opt-in: private endpoint for the Event Hubs namespace in an NSG-protected VNet, public access off. Off by default (cheap demo; consumers must then run inside or be peered to the VNet).')
param privateNetworking bool = false

var suffix = uniqueString(resourceGroup().id)
var tags = { lab: 'wind-turbine-continual-learning', deployed: 'never-from-this-repo' }

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
  properties: { disableLocalAuth: true, minimumTlsVersion: '1.2', publicNetworkAccess: privateNetworking ? 'Disabled' : 'Enabled' }
}

resource telemetryHub 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: eventHubs
  name: 'turbine-telemetry'
  properties: { partitionCount: 4, messageRetentionInDays: 1 }
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: '${prefix}-cosmos-${suffix}'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    disableLocalAuth: true
    capabilities: [ { name: 'EnableServerless' } ]
    locations: [ { locationName: location, failoverPriority: 0 } ]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
  }
}

resource episodesDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmos
  name: 'turbine'
  properties: { resource: { id: 'turbine' } }
}

resource episodes 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: episodesDb
  name: 'episodes'
  properties: {
    resource: {
      id: 'episodes'
      partitionKey: { paths: [ '/turbine_id' ], kind: 'Hash' }
    }
  }
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

resource foundry 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: '${prefix}-ai-${suffix}'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  properties: { customSubDomainName: '${prefix}-ai-${suffix}', disableLocalAuth: true, publicNetworkAccess: 'Enabled' }
}

resource diagnosisDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundry
  name: 'turbine-diagnosis'
  sku: { name: 'DataZoneStandard', capacity: 10 }
  properties: { model: { format: 'OpenAI', name: diagnosisModel, version: modelVersion } }
}

// ---- optional private networking for Event Hubs (off by default; mirrors terraform module private-network) ----
resource nsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = if (privateNetworking) {
  name: '${prefix}-nsg-${suffix}'
  location: location
  tags: tags
  properties: { securityRules: [] } // default rules only; tighten per client policy
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = if (privateNetworking) {
  name: '${prefix}-vnet-${suffix}'
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.50.0.0/16'] }
    subnets: [
      { name: 'pe', properties: { addressPrefix: '10.50.2.0/24', networkSecurityGroup: { id: nsg.id }, privateEndpointNetworkPolicies: 'Disabled' } }
    ]
  }
}

resource evhZone 'Microsoft.Network/privateDnsZones@2020-06-01' = if (privateNetworking) {
  name: 'privatelink.servicebus.windows.net'
  location: 'global'
  tags: tags
}

resource evhZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = if (privateNetworking) {
  parent: evhZone
  name: 'link-${prefix}-${suffix}'
  location: 'global'
  properties: { virtualNetwork: { id: vnet.id }, registrationEnabled: false }
}

resource evhPe 'Microsoft.Network/privateEndpoints@2024-05-01' = if (privateNetworking) {
  name: '${prefix}-pe-evh-${suffix}'
  location: location
  tags: tags
  properties: {
    subnet: { id: vnet!.properties.subnets[0].id }
    privateLinkServiceConnections: [
      { name: 'evh', properties: { privateLinkServiceId: eventHubs.id, groupIds: ['namespace'] } }
    ]
  }
}

resource evhPeDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = if (privateNetworking) {
  parent: evhPe
  name: 'default'
  properties: { privateDnsZoneConfigs: [{ name: 'servicebus', properties: { privateDnsZoneId: evhZone.id } }] }
}

output dataZone string = dataZone
output identityClientId string = identity.properties.clientId
output foundryEndpoint string = foundry.properties.endpoint
