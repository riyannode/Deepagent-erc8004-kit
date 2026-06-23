REPUTATION_REGISTRY_ABI = [
    {
        "type": "function",
        "name": "giveFeedback",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "agentId", "type": "uint256"},
            {"name": "score", "type": "int128"},
            {"name": "feedbackType", "type": "uint8"},
            {"name": "tag", "type": "string"},
            {"name": "metadataURI", "type": "string"},
            {"name": "evidenceURI", "type": "string"},
            {"name": "comment", "type": "string"},
            {"name": "feedbackHash", "type": "bytes32"},
        ],
        "outputs": [],
    }
]
