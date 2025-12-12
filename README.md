# Runna Zone2

Automatically add HR Zone 2 targets to your Runna workouts synced to Garmin watches.

## The Problem

Runna syncs great structured workouts to Garmin, but warmups, cooldowns, and easy intervals don't have HR zone targets. During structured workouts, [Garmin watches ignore your custom HR alerts](https://support.garmin.com/en-US/?faq=RsB4M7L3Nu8VVePzEuICG9) - only targets set within the workout itself will trigger alerts. This means your watch won't alert you if you're going too hard during recovery portions.

## The Solution

This script automatically adds Zone 2 HR targets to:
- Warmup steps
- Cooldown steps
- Recovery steps
- Easy intervals (detected by "conversational", "easy", or "slow" in the description)

It skips:
- Hard intervals ("pushing", "fast", "tempo", "threshold", "race", "sprint")
- Rest steps
- Steps that already have targets (like pace zones)

## Setup (GitHub Actions - Recommended)

Run this automatically once per day without any local setup:

1. **Fork this repository**

   > **Privacy note:** Consider making your fork private. While GitHub Secrets are encrypted and never exposed in logs, a private repo adds an extra layer of security. GitHub Actions work the same on private repos (free tier includes 2,000 minutes/month).

2. **Add your Garmin credentials as secrets**
   - Go to your fork's Settings > Secrets and variables > Actions
   - Click "New repository secret"
   - Add `GARMIN_EMAIL` with your Garmin Connect login (email address or username, depending on your account)
   - Add `GARMIN_PASSWORD` with your Garmin Connect password

3. **Enable GitHub Actions**
   - Go to the Actions tab in your fork
   - Click "I understand my workflows, go ahead and enable them"

4. **Done!** The workflow runs daily at 6am UTC.

5. **To run manually:**
   - Go to your fork's Actions tab (https://github.com/YOUR_USERNAME/runna-zone2/actions)
   - Click "Update Garmin Workouts" in the left sidebar
   - You'll see a banner saying "This workflow has a workflow_dispatch event trigger"
   - Click the "Run workflow" dropdown button on the right
   - Check "Dry run" to preview changes without modifying workouts (recommended for first run)
   - Click the green "Run workflow" button to start it
   - Refresh the page to see the run progress and logs

> **Note:** The first time the action runs, you'll receive an email from Garmin about a login from a new location (GitHub's servers). This is normal and expected.

### Security

- Your credentials are stored in [GitHub Encrypted Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets) - they're encrypted at rest and masked in logs
- Credentials never leave GitHub's infrastructure
- No third-party services or databases involved
- You can delete the secrets anytime from your repo settings

## Setup (Local)

### Requirements

- Python 3.10+
- `pip install garminconnect`

### Usage

```bash
# Set credentials
export GARMIN_EMAIL="your@email.com"
export GARMIN_PASSWORD="yourpassword"

# Preview changes (dry run)
python garmin.py --filter Runna --dry-run --verbose

# Apply changes
python garmin.py --filter Runna --verbose

# List all workouts
python garmin.py --list

# Dump a workout's JSON structure
python garmin.py --dump-workout 12345678
```

### Options

| Option | Description |
|--------|-------------|
| `--filter NAME` | Only process workouts containing NAME (e.g., "Runna") |
| `--dry-run` | Preview changes without updating |
| `--verbose` | Show detailed step-by-step processing |
| `--zone N` | HR zone to add (default: 2) |
| `--list` | List all workouts with IDs |
| `--limit N` | Max workouts to fetch (default: 30) |

### Cron (Local)

To run automatically on your machine:

```bash
crontab -e
```

Add:
```
0 8,12,18 * * * cd /path/to/runna-zone2 && python garmin.py --filter Runna >> garmin.log 2>&1
```

## How It Works

1. Logs into Garmin Connect using the [garminconnect](https://github.com/cyberjunky/python-garminconnect) library
2. Fetches your workouts from the Garmin API
3. For each Runna workout, examines each step
4. Adds HR Zone 2 target to easy steps that don't already have a target
5. Pushes the updated workout back to Garmin

The script is idempotent - running it multiple times won't duplicate changes.

## Supported Workouts

The script detects easy vs hard intervals by looking for keywords in Runna's step descriptions:

| Type | Keywords | Action |
|------|----------|--------|
| Easy | "conversational", "easy", "slow" | Adds Zone 2 HR target |
| Hard | "pushing", "fast", "hard", "tempo", "threshold", "race", "sprint" | Skipped |

**Help wanted:** This has only been tested with the "Returning to Running" plan. If you're on a different Runna plan (5K, 10K, marathon, etc.) and notice workouts that aren't being handled correctly, please open an issue with the workout description so I can add the missing keywords.

Feel free to request other features too - I'll add what I can!

## License

MIT
