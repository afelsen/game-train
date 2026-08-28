#!/bin/sh
set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
vendor_dir="$root_dir/vendor"

mkdir -p "$vendor_dir/fullhouse-bot" "$vendor_dir/rlcard" "$vendor_dir/postflop-solver"

curl -L --fail --silent --show-error \
  https://github.com/advitrocks9/fullhouse-bot/archive/e504793d480b1b975f25258d25939b45c6dbd5a4.tar.gz \
  -o "$vendor_dir/fullhouse-bot.tar.gz"
curl -L --fail --silent --show-error \
  https://github.com/datamllab/rlcard/archive/d7d0a957baf4cc7225a50522adb0164bf130a9d0.tar.gz \
  -o "$vendor_dir/rlcard.tar.gz"
curl -L --fail --silent --show-error \
  https://github.com/b-inary/postflop-solver/archive/9d1509fe5077d019825f833eed04b16d342dfda1.tar.gz \
  -o "$vendor_dir/postflop-solver.tar.gz"

rm -rf "$vendor_dir/fullhouse-bot" "$vendor_dir/rlcard" "$vendor_dir/postflop-solver"
mkdir -p "$vendor_dir/fullhouse-bot" "$vendor_dir/rlcard" "$vendor_dir/postflop-solver"
tar -xzf "$vendor_dir/fullhouse-bot.tar.gz" --strip-components=1 -C "$vendor_dir/fullhouse-bot"
tar -xzf "$vendor_dir/rlcard.tar.gz" --strip-components=1 -C "$vendor_dir/rlcard"
tar -xzf "$vendor_dir/postflop-solver.tar.gz" --strip-components=1 -C "$vendor_dir/postflop-solver"

echo "Expected archive checksums:"
echo "b391e56ce2f44efa9712ddd4434ba3749c5bf81f114e1c3fb4df49c37e78a263  $vendor_dir/fullhouse-bot.tar.gz"
echo "f4a10998df7409408a4de62852a1130ed848f7c9ba176858e5cbc31116b22336  $vendor_dir/rlcard.tar.gz"
echo "11be92079448650db8fde1d5ff14a6d0043cfe7b8061143b627e194d54960055  $vendor_dir/postflop-solver.tar.gz"
echo "Actual archive checksums:"
shasum -a 256 "$vendor_dir/fullhouse-bot.tar.gz" "$vendor_dir/rlcard.tar.gz" "$vendor_dir/postflop-solver.tar.gz"
