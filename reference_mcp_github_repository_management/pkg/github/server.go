package github

type MCPServerConfig struct {
    EnabledTools []string
    EnabledFeatures []string
    DynamicToolsets bool
    ReadOnly bool
    ExcludeTools []string
    TokenScopes []string
    LockdownMode bool
}

type FeatureFlags struct {
    LockdownMode bool
}
