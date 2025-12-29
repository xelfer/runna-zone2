#!/usr/bin/env python3
"""
Garmin HR Zone Injector

This script fetches your scheduled Runna workouts from Garmin Connect,
adds Zone 2 HR targets to warmup/recovery/easy steps, and updates them.

Requirements:
    pip install garminconnect

Usage:
    export GARMIN_EMAIL="your@email.com"
    export GARMIN_PASSWORD="yourpassword"

    python garmin.py --list
    python garmin.py --dry-run --verbose
    python garmin.py
"""

import os
import sys
import json
import argparse
import copy
from typing import Tuple

from garminconnect import Garmin

# Garmin workout step types
EASY_STEP_KEYS = {"warmup", "cooldown", "recovery"}
EASY_STEP_IDS = {1, 2, 3}  # warmup=1, cooldown=2, recovery=3 (rest=4 excluded)

# Description patterns that indicate easy/conversational pace (from Runna)
EASY_DESCRIPTION_PATTERNS = ["conversational", "easy", "slow"]
# Description patterns that indicate hard effort - skip these
HARD_DESCRIPTION_PATTERNS = ["pushing", "fast", "hard", "tempo", "threshold", "race", "sprint"]

HR_ZONE_TARGET_TYPE = {
    "workoutTargetTypeId": 4,
    "workoutTargetTypeKey": "heart.rate.zone"
}
NO_TARGET_TYPE_ID = 1
DEFAULT_HR_ZONE = 2


class GarminHRZoneInjector:
    def __init__(self, email: str, password: str, hr_zone: int = DEFAULT_HR_ZONE):
        self.email = email
        self.password = password
        self.hr_zone = hr_zone
        self.client = None

    def login(self):
        """Login to Garmin Connect"""
        print(f"Logging in as {self.email}...")
        self.client = Garmin(self.email, self.password)
        self.client.login()
        print(f"Logged in as: {self.client.display_name}\n")

    def list_workouts(self, limit: int = 30):
        """List all workouts with their IDs and basic info"""
        workouts = self.client.connectapi("/workout-service/workouts", params={
            "start": 1,
            "limit": limit,
            "myWorkoutsOnly": "true",
            "sharedWorkoutsOnly": "false",
            "orderBy": "WORKOUT_NAME",
            "orderSeq": "ASC",
            "includeAtp": "false"
        })

        print(f"Found {len(workouts)} workouts:\n")
        print(f"{'ID':<12} {'Sport':<10} {'Name':<40}")
        print("-" * 65)

        for w in workouts:
            workout_id = w.get("workoutId", "?")
            sport = w.get("sportType", {}).get("sportTypeKey", "?")
            name = w.get("workoutName", "?")[:38]
            print(f"{workout_id:<12} {sport:<10} {name:<40}")

        return workouts

    def get_workout_details(self, workout_id: int) -> dict:
        """Fetch full workout details by ID"""
        return self.client.connectapi(f"/workout-service/workout/{workout_id}")

    def is_easy_step(self, step: dict) -> bool:
        """Determine if a workout step is an 'easy' step that should get HR zone"""
        step_type = step.get("stepType", {})
        step_key = step_type.get("stepTypeKey", "").lower()
        step_id = step_type.get("stepTypeId")
        description = (step.get("description") or "").lower()

        # Check description for hard effort indicators - never add HR zone to these
        for pattern in HARD_DESCRIPTION_PATTERNS:
            if pattern in description:
                return False

        # Warmup, cooldown, recovery are always easy
        if step_key in EASY_STEP_KEYS or step_id in EASY_STEP_IDS:
            return True

        # For intervals, only add HR zone if description indicates easy pace
        if step_key == "interval" or step_id == 3:
            for pattern in EASY_DESCRIPTION_PATTERNS:
                if pattern in description:
                    return True
            return False  # Interval without easy indicator = skip

        return False

    def has_no_target(self, step: dict) -> bool:
        """Check if step has no target set (meaning we can add HR zone)"""
        target_type = step.get("targetType")
        if target_type is None:
            return True
        target_id = target_type.get("workoutTargetTypeId")
        if target_id is None or target_id == NO_TARGET_TYPE_ID:
            return True
        return False

    def should_add_hr_zone(self, step: dict) -> bool:
        """Determine if a workout step should have HR zone target added"""
        return self.is_easy_step(step) and self.has_no_target(step)

    def add_hr_zone_to_step(self, step: dict) -> dict:
        """Add HR zone target to a workout step"""
        step["targetType"] = copy.deepcopy(HR_ZONE_TARGET_TYPE)
        step["targetValueOne"] = self.hr_zone
        step["targetValueTwo"] = None
        step["zoneNumber"] = self.hr_zone
        return step

    def describe_step(self, step: dict) -> str:
        """Get a human-readable description of a step"""
        step_type = step.get("stepType", {}).get("stepTypeKey", "?")
        end_condition = step.get("endCondition", {}).get("conditionTypeKey", "?")
        end_value = step.get("endConditionValue")

        if end_condition == "time" and end_value:
            duration = f"{int(end_value/60)}:{int(end_value%60):02d}"
        elif end_condition == "distance" and end_value:
            duration = f"{end_value}m"
        else:
            duration = end_condition

        target_type = (step.get("targetType") or {}).get("workoutTargetTypeKey", "none")
        target_val = step.get("targetValueOne", "")

        return f"{step_type} ({duration}) -> target: {target_type} {target_val}"

    def process_workout_steps(self, steps: list, modified_count: int = 0, verbose: bool = False) -> Tuple[list, int]:
        """Recursively process workout steps, including nested repeat groups"""
        processed_steps = []

        for step in steps:
            if "workoutSteps" in step:
                nested_steps, modified_count = self.process_workout_steps(
                    step["workoutSteps"], modified_count, verbose
                )
                step["workoutSteps"] = nested_steps
                processed_steps.append(step)
            else:
                if self.should_add_hr_zone(step):
                    if verbose:
                        print(f"    + {self.describe_step(step)} -> Adding Zone {self.hr_zone}")
                    step = self.add_hr_zone_to_step(step)
                    modified_count += 1
                else:
                    if verbose:
                        print(f"    - {self.describe_step(step)} -> Skip")
                processed_steps.append(step)

        return processed_steps, modified_count

    def modify_workout(self, workout: dict, verbose: bool = False) -> Tuple[dict, int]:
        """Modify a workout to add HR zone targets to appropriate steps"""
        workout_name = workout.get("workoutName", "Unknown")

        if "workoutSegments" not in workout:
            print(f"  No workout segments found in '{workout_name}'")
            return workout, 0

        total_modified = 0

        for segment in workout["workoutSegments"]:
            if "workoutSteps" in segment:
                segment["workoutSteps"], modified = self.process_workout_steps(
                    segment["workoutSteps"], 0, verbose
                )
                total_modified += modified

        return workout, total_modified

    def update_workout(self, workout: dict) -> dict:
        """Push updated workout back to Garmin Connect"""
        workout_id = workout.get("workoutId")
        return self.client.garth.put(
            "connectapi",
            f"/workout-service/workout/{workout_id}",
            json=workout
        )

    def process_all_workouts(self, dry_run: bool = False, limit: int = 20, verbose: bool = False, filter_name: str = None):
        """Main processing loop - fetch, modify, and update workouts"""
        workouts = self.client.connectapi("/workout-service/workouts", params={
            "start": 1,
            "limit": limit,
            "myWorkoutsOnly": "true",
            "sharedWorkoutsOnly": "false",
            "includeAtp": "false"
        })

        print(f"Found {len(workouts)} workouts")
        print("-" * 50)

        processed = 0
        modified_total = 0

        for workout_summary in workouts:
            workout_id = workout_summary.get("workoutId")
            workout_name = workout_summary.get("workoutName", "Unknown")

            sport_type = workout_summary.get("sportType", {}).get("sportTypeKey", "")
            if sport_type != "running":
                if verbose:
                    print(f"Skip '{workout_name}' (sport: {sport_type})")
                continue

            if filter_name and filter_name.lower() not in workout_name.lower():
                continue

            print(f"\nProcessing: {workout_name} (ID: {workout_id})")

            workout = self.get_workout_details(workout_id)
            modified_workout, modified_count = self.modify_workout(workout, verbose)

            if modified_count == 0:
                print(f"  No changes needed")
                continue

            print(f"  Modified {modified_count} steps to add Zone {self.hr_zone} HR target")
            modified_total += modified_count

            if dry_run:
                print(f"  DRY RUN - would update workout")
            else:
                try:
                    print(f"  Updating workout...")
                    self.update_workout(modified_workout)
                    print(f"  Updated successfully")
                    processed += 1
                except Exception as e:
                    print(f"  Failed to update: {e}")
                    print(f"     You may need to manually recreate this workout")

        print(f"\n{'='*50}")
        print(f"Summary: {modified_total} steps modified across {processed} workouts")


def main():
    parser = argparse.ArgumentParser(
        description="Add HR zone targets to Garmin workouts synced from Runna",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all workouts to find IDs
  %(prog)s --list

  # Dump a specific workout to see its JSON structure
  %(prog)s --dump-workout 12345678

  # Preview changes without actually updating
  %(prog)s --dry-run --verbose

  # Apply changes to all running workouts
  %(prog)s

  # Only process workouts with "Runna" in the name
  %(prog)s --filter "Runna"
"""
    )
    parser.add_argument(
        "--email", "-e",
        default=os.environ.get("GARMIN_EMAIL"),
        help="Garmin Connect email (or set GARMIN_EMAIL env var)"
    )
    parser.add_argument(
        "--password", "-p",
        default=os.environ.get("GARMIN_PASSWORD"),
        help="Garmin Connect password (or set GARMIN_PASSWORD env var)"
    )
    parser.add_argument(
        "--zone", "-z",
        type=int,
        default=DEFAULT_HR_ZONE,
        help=f"HR zone to add to easy steps (default: {DEFAULT_HR_ZONE})"
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Preview changes without updating"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed step-by-step processing"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=30,
        help="Maximum number of workouts to fetch (default: 30)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Just list all workouts with their IDs"
    )
    parser.add_argument(
        "--dump-workout",
        type=int,
        metavar="WORKOUT_ID",
        help="Dump the full JSON for a specific workout ID (for debugging)"
    )
    parser.add_argument(
        "--filter", "-f",
        metavar="NAME",
        help="Only process workouts containing this text in their name"
    )

    args = parser.parse_args()

    if not args.email or not args.password:
        print("Error: Garmin credentials required")
        print("\nSet environment variables:")
        print("  export GARMIN_EMAIL='your@email.com'")
        print("  export GARMIN_PASSWORD='yourpassword'")
        print("\nOr use command line arguments:")
        print("  --email your@email.com --password yourpass")
        sys.exit(1)

    injector = GarminHRZoneInjector(args.email, args.password, args.zone)

    try:
        injector.login()

        if args.list:
            injector.list_workouts(limit=args.limit)
        elif args.dump_workout:
            print(f"Fetching workout {args.dump_workout}...")
            workout = injector.get_workout_details(args.dump_workout)
            print("\n" + json.dumps(workout, indent=2))
        else:
            if args.dry_run:
                print("DRY RUN MODE - No changes will be made\n")
            injector.process_all_workouts(
                dry_run=args.dry_run,
                limit=args.limit,
                verbose=args.verbose,
                filter_name=args.filter
            )

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\nDone!")


if __name__ == "__main__":
    main()
