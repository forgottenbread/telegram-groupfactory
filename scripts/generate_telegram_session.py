#!/usr/bin/env python3
"""Generate a Telethon StringSession for TELETHON_TOKEN.

Examples:
  TELETHON_API_ID=123456 TELETHON_API_HASH=abc123 \
    python3 scripts/generate_telegram_session.py

  python3 scripts/generate_telegram_session.py \
    --api-id 123456 \
    --api-hash abc123 \
    --phone +391234567890
"""

import argparse
import asyncio
import os
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a Telethon StringSession for the TELETHON_TOKEN secret."
    )
    parser.add_argument(
        "--api-id",
        default=os.environ.get("TELETHON_API_ID"),
        help="Telegram API ID. Defaults to TELETHON_API_ID.",
    )
    parser.add_argument(
        "--api-hash",
        default=os.environ.get("TELETHON_API_HASH"),
        help="Telegram API hash. Defaults to TELETHON_API_HASH.",
    )
    parser.add_argument(
        "--phone",
        default=os.environ.get("TELETHON_PHONE"),
        help="Telegram user phone number. Defaults to TELETHON_PHONE.",
    )

    args = parser.parse_args()
    if not args.api_id:
        parser.error("--api-id or TELETHON_API_ID is required")
    try:
        args.api_id = int(args.api_id)
    except ValueError:
        parser.error("--api-id or TELETHON_API_ID must be an integer")
    if not args.api_hash:
        parser.error("--api-hash or TELETHON_API_HASH is required")
    return args


async def generate_session(args: argparse.Namespace) -> str:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(), args.api_id, args.api_hash)
    try:
        phone = args.phone or input("Telegram phone number, including country code: ")
        await client.start(phone=phone)
        return client.session.save()
    finally:
        await client.disconnect()


def main() -> int:
    args = parse_args()
    print(
        "Starting Telegram user login. The final stdout line is the TELETHON_TOKEN value.",
        file=sys.stderr,
    )
    session_string = asyncio.run(generate_session(args))
    if not session_string:
        print("Failed to generate a session string.", file=sys.stderr)
        return 1

    print(session_string)
    print("Store this value as TELETHON_TOKEN in the Kubernetes Secret.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
