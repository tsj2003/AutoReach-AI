targetScope = 'resourceGroup'

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Short prefix used to name Azure resources.')
param namePrefix string = 'attainly'

@description('Application tags applied to all resources.')
param tags object = {
  application: 'attainly'
  managedBy: 'app-onboard'
  'app-onboard-skill': 'true'
  'app-onboard-session-id': '9e432501-d3da-4279-bfe5-6060f36cb5f8'
  'created-at': '2026-07-28T07:49:13Z'
  environment: 'prod'
  'deployed-by': 'tarandeepjuneja11@gmail.com'
}

@description('Container image used by all Container Apps. The workflow updates this after pushing a build.')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Optional Microsoft Entra object ID for the deployer. When provided, grants Key Vault Secrets Officer on the generated vault.')
param deployerObjectId string = ''

@description('PostgreSQL administrator login.')
param postgresAdminLogin string = 'autoreachadmin'

@secure()
@description('PostgreSQL administrator password.')
param postgresAdminPassword string

@secure()
@description('Shared JWT signing secret.')
param jwtSecret string

@secure()
@description('Shared session secret.')
param sessionSecret string

@secure()
@description('Fernet key used to encrypt stored credentials.')
param credentialEncryptionKey string

@secure()
@description('Redis/Valkey connection URL used by Celery, mailbox health, and dispatch queues. Provide an existing endpoint; this template does not provision Redis because Azure Cache creation is region/SKU restricted for this subscription.')
param redisUrlOverride string

@description('Public base URL for the deployed application.')
param publicBaseUrl string = ''

@description('Google OAuth client ID.')
param googleClientId string = ''

@secure()
@description('Google OAuth client secret.')
param googleClientSecret string = ''

@description('Google Sign-In client ID.')
param googleSignInClientId string = ''

@secure()
@description('Gemini API key.')
param geminiApiKey string = ''

@secure()
@description('OpenAI API key.')
param openAiApiKey string = ''

@secure()
@description('Anthropic API key.')
param anthropicApiKey string = ''

@secure()
@description('Azure AI API key.')
param azureApiKey string = ''

@description('Phoenix endpoint used for tracing.')
param phoenixEndpoint string = ''

@secure()
@description('Webhook secret for Cal.com.')
param calcomWebhookSecret string = ''

@secure()
@description('Sentry DSN.')
param sentryDsn string = ''

@secure()
@description('PostHog API key.')
param posthogApiKey string = ''

@description('PostHog host URL.')
param posthogHost string = 'https://us.i.posthog.com'

@secure()
@description('Firecrawl API key.')
param firecrawlApiKey string = ''

@description('Razorpay key ID.')
param razorpayKeyId string = ''

@secure()
@description('Razorpay key secret.')
param razorpayKeySecret string = ''

@description('Gmail sender address.')
param gmailSender string = ''

@description('Path to the Gmail token file inside the container.')
param gmailTokenPath string = 'token.json'

@description('Whether Gmail dry-run mode should stay enabled.')
param gmailDryRun string = '1'

@description('Worker queue list for Celery.')
param workerQueues string = 'engine,maintenance,standard-agents'

@description('Hours of history to load for intent ingestion.')
param intentHoursBack string = '24'

var uniqueSuffix = uniqueString(resourceGroup().id)
var logAnalyticsName = toLower('${namePrefix}-law')
var containerRegistryName = toLower('ar${uniqueSuffix}')
var keyVaultName = toLower('kv${uniqueSuffix}')
var postgresServerName = toLower('pg${uniqueSuffix}')
var postgresDatabaseName = 'autoreach'
var webAppName = '${namePrefix}-web'
var workerAppName = '${namePrefix}-worker'
var beatAppName = '${namePrefix}-beat'
var keyVaultSecretsOfficerRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7')

var databaseUrl = 'postgresql://${postgresAdminLogin}:${postgresAdminPassword}@${postgresServer.properties.fullyQualifiedDomainName}:5432/${postgresDatabaseName}?sslmode=require'
var redisUrl = redisUrlOverride

var requiredSecretValues = [
  {
    name: 'database-url'
    value: databaseUrl
  }
  {
    name: 'redis-url'
    value: redisUrl
  }
  {
    name: 'jwt-secret'
    value: jwtSecret
  }
  {
    name: 'session-secret'
    value: sessionSecret
  }
  {
    name: 'credential-encryption-key'
    value: credentialEncryptionKey
  }
  {
    name: 'acr-password'
    value: containerRegistry.listCredentials().passwords[0].value
  }
]

var optionalSecretValues = concat(
  empty(googleClientSecret) ? [] : [
    {
      name: 'google-client-secret'
      value: googleClientSecret
    }
  ],
  empty(geminiApiKey) ? [] : [
    {
      name: 'gemini-api-key'
      value: geminiApiKey
    }
  ],
  empty(openAiApiKey) ? [] : [
    {
      name: 'openai-api-key'
      value: openAiApiKey
    }
  ],
  empty(anthropicApiKey) ? [] : [
    {
      name: 'anthropic-api-key'
      value: anthropicApiKey
    }
  ],
  empty(azureApiKey) ? [] : [
    {
      name: 'azure-api-key'
      value: azureApiKey
    }
  ],
  empty(calcomWebhookSecret) ? [] : [
    {
      name: 'calcom-webhook-secret'
      value: calcomWebhookSecret
    }
  ],
  empty(sentryDsn) ? [] : [
    {
      name: 'sentry-dsn'
      value: sentryDsn
    }
  ],
  empty(posthogApiKey) ? [] : [
    {
      name: 'posthog-api-key'
      value: posthogApiKey
    }
  ],
  empty(firecrawlApiKey) ? [] : [
    {
      name: 'firecrawl-api-key'
      value: firecrawlApiKey
    }
  ],
  empty(razorpayKeySecret) ? [] : [
    {
      name: 'razorpay-key-secret'
      value: razorpayKeySecret
    }
  ]
)

var commonSecretValues = concat(requiredSecretValues, optionalSecretValues)

var baseEnvVars = [
  {
    name: 'DATABASE_URL'
    secretRef: 'database-url'
  }
  {
    name: 'REDIS_URL'
    secretRef: 'redis-url'
  }
  {
    name: 'AUTOREACH_JWT_SECRET'
    secretRef: 'jwt-secret'
  }
  {
    name: 'AUTOREACH_SESSION_SECRET'
    secretRef: 'session-secret'
  }
  {
    name: 'AUTOREACH_CREDENTIAL_ENCRYPTION_KEY'
    secretRef: 'credential-encryption-key'
  }
  {
    name: 'AUTOREACH_ENABLE_CONSOLE'
    value: '0'
  }
  {
    name: 'AUTOREACH_RUNTIME_SMART_DISPATCH'
    value: '1'
  }
  {
    name: 'AUTOREACH_WORKER_QUEUES'
    value: workerQueues
  }
  {
    name: 'AUTOREACH_INTENT_HOURS_BACK'
    value: intentHoursBack
  }
  {
    name: 'AUTOREACH_PUBLIC_BASE_URL'
    value: publicBaseUrl
  }
  {
    name: 'GOOGLE_CLIENT_ID'
    value: googleClientId
  }
  {
    name: 'GOOGLE_SIGNIN_CLIENT_ID'
    value: googleSignInClientId
  }
  {
    name: 'AUTOREACH_PHOENIX_ENDPOINT'
    value: phoenixEndpoint
  }
  {
    name: 'POSTHOG_HOST'
    value: posthogHost
  }
  {
    name: 'RAZORPAY_KEY_ID'
    value: razorpayKeyId
  }
  {
    name: 'AUTOREACH_GMAIL_SENDER'
    value: gmailSender
  }
  {
    name: 'AUTOREACH_GMAIL_TOKEN_PATH'
    value: gmailTokenPath
  }
  {
    name: 'AUTOREACH_GMAIL_DRY_RUN'
    value: gmailDryRun
  }
]

var optionalEnvVars = concat(
  empty(googleClientSecret) ? [] : [
    {
      name: 'GOOGLE_CLIENT_SECRET'
      secretRef: 'google-client-secret'
    }
  ],
  empty(geminiApiKey) ? [] : [
    {
      name: 'GEMINI_API_KEY'
      secretRef: 'gemini-api-key'
    }
  ],
  empty(openAiApiKey) ? [] : [
    {
      name: 'OPENAI_API_KEY'
      secretRef: 'openai-api-key'
    }
  ],
  empty(anthropicApiKey) ? [] : [
    {
      name: 'ANTHROPIC_API_KEY'
      secretRef: 'anthropic-api-key'
    }
  ],
  empty(azureApiKey) ? [] : [
    {
      name: 'AZURE_API_KEY'
      secretRef: 'azure-api-key'
    }
  ],
  empty(calcomWebhookSecret) ? [] : [
    {
      name: 'CALCOM_WEBHOOK_SECRET'
      secretRef: 'calcom-webhook-secret'
    }
  ],
  empty(sentryDsn) ? [] : [
    {
      name: 'SENTRY_DSN'
      secretRef: 'sentry-dsn'
    }
  ],
  empty(posthogApiKey) ? [] : [
    {
      name: 'POSTHOG_API_KEY'
      secretRef: 'posthog-api-key'
    }
  ],
  empty(firecrawlApiKey) ? [] : [
    {
      name: 'FIRECRAWL_API_KEY'
      secretRef: 'firecrawl-api-key'
    }
  ],
  empty(razorpayKeySecret) ? [] : [
    {
      name: 'RAZORPAY_KEY_SECRET'
      secretRef: 'razorpay-key-secret'
    }
  ]
)

var commonEnvVars = concat(baseEnvVars, optionalEnvVars)

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2025-02-01' = {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-06-01-preview' = {
  name: containerRegistryName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
    anonymousPullEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2024-11-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    publicNetworkAccess: 'Disabled'
    sku: {
      family: 'A'
      name: 'standard'
    }
  }
}

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: postgresServerName
  location: location
  tags: tags
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    administratorLogin: postgresAdminLogin
    administratorLoginPassword: postgresAdminPassword
    version: '16'
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
  }
}

resource postgresDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  name: postgresDatabaseName
  parent: postgresServer
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

resource postgresAllowAzureServices 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  name: 'AllowAzureServices'
  parent: postgresServer
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2024-10-02-preview' = {
  name: '${namePrefix}-env'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    publicNetworkAccess: 'Enabled'
  }
}

resource webApp 'Microsoft.App/containerApps@2025-01-01' = {
  name: webAppName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        allowInsecure: false
        transport: 'auto'
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          username: containerRegistry.name
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: commonSecretValues
    }
    template: {
      containers: [
        {
          name: 'autoreach-web'
          image: containerImage
          env: commonEnvVars
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
      }
    }
  }
}

resource workerApp 'Microsoft.App/containerApps@2025-01-01' = {
  name: workerAppName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [
        {
          server: containerRegistry.properties.loginServer
          username: containerRegistry.name
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: commonSecretValues
    }
    template: {
      containers: [
        {
          name: 'autoreach-worker'
          image: containerImage
          command: [
            'celery'
          ]
          args: [
            '-A'
            'celery_worker.celery_app'
            'worker'
            '--loglevel=info'
            '--concurrency=2'
            '-Q'
            workerQueues
          ]
          env: commonEnvVars
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 2
      }
    }
  }
}

resource beatApp 'Microsoft.App/containerApps@2025-01-01' = {
  name: beatAppName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [
        {
          server: containerRegistry.properties.loginServer
          username: containerRegistry.name
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: commonSecretValues
    }
    template: {
      containers: [
        {
          name: 'autoreach-beat'
          image: containerImage
          command: [
            'celery'
          ]
          args: [
            '-A'
            'celery_worker.celery_app'
            'beat'
            '--loglevel=info'
          ]
          env: commonEnvVars
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

resource deployerKeyVaultSecretsOfficer 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployerObjectId)) {
  name: guid(keyVault.id, deployerObjectId, 'key-vault-secrets-officer')
  scope: keyVault
  properties: {
    roleDefinitionId: keyVaultSecretsOfficerRoleDefinitionId
    principalId: deployerObjectId
    principalType: 'User'
  }
}

output containerRegistryLoginServer string = containerRegistry.properties.loginServer
output containerAppsEnvironmentId string = containerAppsEnvironment.id
output keyVaultUri string = keyVault.properties.vaultUri
output logAnalyticsWorkspaceId string = logAnalytics.properties.customerId
output webAppFqdn string = webApp.properties.configuration.ingress.fqdn
output webAppUrl string = 'https://${webApp.properties.configuration.ingress.fqdn}/'
output cockpitUrl string = 'https://${webApp.properties.configuration.ingress.fqdn}/app/'
output postgresFqdn string = postgresServer.properties.fullyQualifiedDomainName
output redisHostName string = 'external-redis-configured'
