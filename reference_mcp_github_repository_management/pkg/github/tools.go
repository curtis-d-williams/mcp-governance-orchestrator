package github

var (
    ToolsetMetadataAll = inventory.ToolsetMetadata{
        ID:          "all",
        Description: "all",
    }
    ToolsetMetadataDefault = inventory.ToolsetMetadata{
        ID:          "default",
        Description: "default",
    }
    ToolsetMetadataContext = inventory.ToolsetMetadata{
        ID:          "context",
        Description: "context",
        Default:     true,
    }
    ToolsetMetadataRepos = inventory.ToolsetMetadata{
        ID:          "repos",
        Description: "repos",
        Default:     true,
    }
    ToolsetMetadataCopilotSpaces = inventory.ToolsetMetadata{
        ID:          "copilot_spaces",
        Description: "copilot spaces",
    }
)

func AllTools(t any) []inventory.ServerTool {
    return []inventory.ServerTool{
        GetMe(t),
        CreatePullRequest(t),
    }
}

func RemoteOnlyToolsets() []inventory.ToolsetMetadata {
    return []inventory.ToolsetMetadata{
        ToolsetMetadataCopilotSpaces,
    }
}
