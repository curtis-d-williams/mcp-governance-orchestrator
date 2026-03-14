package ghmcp

type StdioServerConfig struct {
    EnabledTools []string
    EnabledFeatures []string
    DynamicToolsets bool
    ReadOnly bool
    ExcludeTools []string
    LockdownMode bool
}
