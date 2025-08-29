# Zotero Daily Digest

Automatically generates and sends daily summaries of your Zotero library activity, including new papers added and papers with recent notes/annotations. Supports both console output and Slack notifications.

## Features

- **Daily summaries** of Zotero library activity
- **Weekend logic**: On Mondays, extends window to include the full weekend
- **Group library support** with filtering of auto-generated annotations
- **Slack integration** via webhooks
- **Time-based filtering** to focus on meaningful activity
- **Flexible configuration** via environment variables

## Quick Start

1. **Clone and setup**:
   ```bash
   git clone <repo-url>
   cd zotero-digest
   ```

2. **Install dependencies**:
   ```bash
   pip3 install requests
   ```

3. **Configure credentials** (see Setup section below)

4. **Run manually**:
   ```bash
   python3 zotero_app.py
   ```

## Setup

### 1. Zotero API Key

1. Go to [https://www.zotero.org/settings/keys](https://www.zotero.org/settings/keys)
2. Create a new private key with read permissions for your library
3. Add to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.):
   ```bash
   export ZOTERO_API_KEY="your-api-key-here"
   ```

### 2. Slack Integration (Optional)

1. Create a Slack app:
   - Go to [https://api.slack.com/apps](https://api.slack.com/apps)
   - Click "Create New App" → "From scratch"
   - Name it "Zotero Digest" and select your workspace

2. Enable Incoming Webhooks:
   - Go to "Incoming Webhooks" in the left sidebar
   - Toggle it ON
   - Click "Add New Webhook to Workspace"
   - Choose your target channel
   - Copy the webhook URL

3. Add to your shell profile:
   ```bash
   export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
   ```

### 3. Library Configuration

Edit `zotero_digest.env` to configure your library settings:

```bash
# Library settings
LIBRARY_TYPE=groups          # "users" or "groups"
LIBRARY_ID=1234567          # Your numeric library/group ID
LOCAL_TZ=America/Los_Angeles # Your timezone
SKIP_WEEKENDS=1             # Skip running on weekends (0=run always)
DEBUG_FILTER=0              # Show debug info (1=enabled)

# Optional settings
WINDOW_DAYS=1                        # Days to look back (default: 1)
ZOTERO_COLLECTION=ABCD1234          # 8-char collection key to filter
AUTO_ANNOTATION_THRESHOLD=1          # Minutes threshold for auto-annotations
PAPER_TYPES=journalArticle,preprint  # Custom paper types (comma-separated)
```

### 4. Reload Environment

```bash
source ~/.bashrc  # or ~/.zshrc
```

## Usage

### Manual Execution
```bash
python3 zotero_app.py
```

### Using the Shell Script
```bash
./zotero_digest.sh
```

## Cron Job Setup

To run automatically every weekday at 9 AM:

### 1. Make script executable
```bash
chmod +x /path/to/zotero-digest/zotero_digest.sh
```

### 2. Edit crontab
```bash
crontab -e
```

### 3. Add cron entry
```bash
# Zotero Daily Digest - weekdays at 9 AM
0 9 * * 1-5 /path/to/zotero-digest/zotero_digest.sh >> /path/to/zotero-digest/cron.log 2>&1
```

**Note**: The shell script automatically sources `~/.bashrc` to access your `ZOTERO_API_KEY` and `SLACK_WEBHOOK_URL` environment variables.

### Alternative: Set variables directly in crontab
If you prefer not to rely on shell profile loading:
```bash
# In crontab -e:
ZOTERO_API_KEY=your-api-key-here
SLACK_WEBHOOK_URL=your-webhook-url-here
0 9 * * 1-5 /path/to/zotero-digest/zotero_digest.sh >> /path/to/zotero-digest/cron.log 2>&1
```

## Environment Variables Reference

### Required
- `ZOTERO_API_KEY`: Your Zotero API key (set in shell profile)

### Optional
- `SLACK_WEBHOOK_URL`: Slack webhook URL for notifications (set in shell profile)
- `LIBRARY_TYPE`: "users" or "groups" (default: "users")
- `LIBRARY_ID`: Numeric library/group ID (auto-detected if not set)
- `GROUP_NAME`: Group name for auto-discovery (groups only)
- `LOCAL_TZ`: Your timezone (default: "America/Los_Angeles")
- `WINDOW_DAYS`: Days to look back (default: 1)
- `SKIP_WEEKENDS`: Skip weekend execution (default: 1)
- `ZOTERO_COLLECTION`: 8-character collection key to filter
- `DEBUG_FILTER`: Show filtering debug info (default: 0)
- `AUTO_ANNOTATION_THRESHOLD`: Minutes threshold for auto-annotations (default: 1)
- `PAPER_TYPES`: Custom paper types, comma-separated

## Troubleshooting

### Common Issues

1. **"No module named 'requests'"**:
   ```bash
   pip3 install requests
   ```

2. **API key errors**:
   - Verify key is correct at [https://www.zotero.org/settings/keys](https://www.zotero.org/settings/keys)
   - Ensure key has read permissions for your library

3. **Group access errors**:
   - Verify you're a member of the group
   - Check that your API key has group access permissions

4. **Cron not running**:
   - Check cron is running: `sudo systemctl status cron`
   - Verify paths are absolute in crontab
   - Check logs: `tail -f /path/to/zotero-digest/cron.log`

5. **Slack not working**:
   - Verify webhook URL is correct
   - Test manually: `curl -X POST -H 'Content-type: application/json' --data '{"text":"Test"}' YOUR_WEBHOOK_URL`

### Debug Mode
Enable debug output to troubleshoot filtering:
```bash
DEBUG_FILTER=1 python3 zotero_app.py
```

## File Structure

```
zotero-digest/
├── zotero_app.py           # Main application
├── zotero_digest.sh        # Shell wrapper script
├── zotero_digest.env       # Configuration file
├── state_*.json           # State files (auto-generated)
├── cron.log               # Cron execution log
└── README.md              # This file
```

## How It Works

1. **Fetches recent items** from your Zotero library (last 100 modified)
2. **Filters by time window** (default: last 24 hours, extends to 72 hours on Mondays)
3. **Categorizes items**:
   - New papers added to library
   - Papers with recent notes/annotations (meaningful activity only)
4. **Outputs summary** to console and optionally to Slack
5. **Saves state** for efficient future runs

### Weekend Logic
- **Saturday/Sunday**: No digest generated (configurable with `SKIP_WEEKENDS=0`)
- **Monday**: Automatically extends window to cover the full weekend (Friday-Monday)

### Group Library Features
- **Multi-user support**: Shows activity from all group members
- **Auto-annotation filtering**: Excludes annotations created within 1 minute of paper upload
- **Meaningful activity**: Focuses on human-generated notes and annotations