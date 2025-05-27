# Environment Setup

## Required Environment Variables

Create a `.env` file in the project root with the following variables:

```bash
# Source Braintrust Organization
BT_SOURCE_API_KEY=your_source_org_api_key_here
BT_SOURCE_URL=https://api.braintrust.dev  # or your self-hosted instance

# Destination Braintrust Organization  
BT_DEST_API_KEY=your_destination_org_api_key_here
BT_DEST_URL=https://api.braintrust.dev  # or your self-hosted instance

# Migration Configuration (Optional)
MIGRATION_BATCH_SIZE=100
MIGRATION_MAX_RETRIES=3
MIGRATION_RETRY_DELAY=1.0
MIGRATION_TIMEOUT=300
MIGRATION_PARALLEL_PROJECTS=3

# Logging Configuration (Optional)
LOG_LEVEL=INFO
LOG_FORMAT=json  # json or text
LOG_FILE=  # Optional: path to log file, defaults to stdout

# Checkpointing (Optional)
CHECKPOINT_DIR=./checkpoints
CHECKPOINT_INTERVAL=10  # Save checkpoint every N processed items
```

## Getting API Keys

1. **Source Organization**: Log into your source Braintrust organization and navigate to Settings → API Keys
2. **Destination Organization**: Log into your destination Braintrust organization and navigate to Settings → API Keys

## Self-Hosted Instances

If you're using self-hosted Braintrust instances, update the `BT_SOURCE_URL` and `BT_DEST_URL` accordingly:

```bash
BT_SOURCE_URL=https://your-source-instance.company.com
BT_DEST_URL=https://your-dest-instance.company.com
```

## Security Notes

- Never commit `.env` files to version control
- Use environment-specific API keys with appropriate permissions
- Consider using a secrets manager for production deployments 