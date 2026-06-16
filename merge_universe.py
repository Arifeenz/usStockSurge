"""
merge_universe.py — รวม filter_universe.json (44 หุ้นล่าสุด)
                    เข้ากับ filter_universe_base.json (หุ้นทั้งตลาด)

วิธีใช้:
    python merge_universe.py                          # ใช้ default paths
    python merge_universe.py --base my_base.json      # ระบุ base file เอง
    python merge_universe.py --local my_local.json    # ระบุ local file เอง
    python merge_universe.py --output result.json     # ระบุ output file เอง
    python merge_universe.py --dry-run                # ดูผลโดยไม่ save

Flow:
    filter_universe_base.json  (หุ้นทั้งตลาด — อัปเดตจาก wisarut)
    +
    filter_universe.json       (44 หุ้น — อัปเดตทุกวันจาก fetch_universe.py)
    ↓ merge_universe.py
    filter_universe.json       (หุ้นทั้งตลาด + 44 หุ้นล่าสุด)
"""

import argparse
import json
import os
from datetime import datetime


DEFAULT_BASE  = "filter_universe_base.json"   # หุ้นทั้งตลาดจาก wisarut
DEFAULT_LOCAL = "filter_universe.json"         # 44 หุ้นล่าสุดจาก fetch_universe.py
DEFAULT_OUTPUT = "filter_universe.json"        # output (save ทับ local)


def load_json(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = list(data.values())
    return data


def get_date(row: dict) -> str:
    """ดึงวันที่จาก row — รองรับหลาย field name"""
    for field in ("date", "last_date", "latest_date"):
        v = row.get(field)
        if v:
            return str(v)[:10]
    return ""


def merge(base: list, local: list, verbose: bool = True) -> list:
    """
    Merge local เข้า base โดย:
    - ถ้า symbol ซ้อนทับกัน → ใช้ข้อมูลที่ใหม่กว่า
    - ถ้า symbol ไม่ซ้อน → คงของเดิมไว้
    """
    # index base ด้วย symbol
    base_map = {str(r.get("symbol", "")).upper(): r for r in base}

    updated = 0
    added   = 0
    skipped = 0

    for row in local:
        sym = str(row.get("symbol", "")).upper()
        if not sym:
            continue

        if sym in base_map:
            base_date  = get_date(base_map[sym])
            local_date = get_date(row)

            if local_date >= base_date:
                base_map[sym] = row
                updated += 1
            else:
                skipped += 1
                if verbose:
                    print(f"  ⏭ {sym}: local ({local_date}) เก่ากว่า base ({base_date}) — ข้ามไป")
        else:
            base_map[sym] = row
            added += 1

    result = list(base_map.values())

    if verbose:
        print(f"\n  📊 สรุป merge:")
        print(f"     base    : {len(base):,} หุ้น")
        print(f"     local   : {len(local):,} หุ้น")
        print(f"     updated : {updated:,} หุ้น (local ใหม่กว่า → ใช้ local)")
        print(f"     added   : {added:,} หุ้น (ไม่มีใน base → เพิ่มใหม่)")
        print(f"     skipped : {skipped:,} หุ้น (base ใหม่กว่า → คง base)")
        print(f"     output  : {len(result):,} หุ้น")

    return result


def run(args):
    base_path   = args.base
    local_path  = args.local
    output_path = args.output

    # ── ตรวจสอบไฟล์ ──
    if not os.path.exists(base_path):
        raise FileNotFoundError(
            f"❌ ไม่พบ base file: {base_path}\n"
            f"   ให้เปลี่ยนชื่อ filter_universe_converted.json เป็น {base_path} ก่อน"
        )
    if not os.path.exists(local_path):
        raise FileNotFoundError(
            f"❌ ไม่พบ local file: {local_path}\n"
            f"   รัน fetch_universe.py ก่อน"
        )

    print(f"\n🔀 Merge Universe")
    print(f"   base  : {base_path}")
    print(f"   local : {local_path}")
    print(f"   output: {output_path}")
    print()

    # ── โหลด ──
    print("📂 โหลดไฟล์...")
    base  = load_json(base_path)
    local = load_json(local_path)

    base_date  = max((get_date(r) for r in base  if get_date(r)), default="?")
    local_date = max((get_date(r) for r in local if get_date(r)), default="?")

    print(f"   base  : {len(base):,} หุ้น  (date ล่าสุด: {base_date})")
    print(f"   local : {len(local):,} หุ้น  (date ล่าสุด: {local_date})")

    # ── merge ──
    print("\n🔄 กำลัง merge...")
    result = merge(base, local, verbose=not args.quiet)

    # ── dry run ──
    if args.dry_run:
        print(f"\n🔍 --dry-run: ไม่ได้ save ไฟล์")
        return

    # ── save ──
    # backup output เดิมก่อนถ้ามีอยู่แล้ว
    if os.path.exists(output_path) and not args.no_backup:
        backup = output_path.replace(".json", f"_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        os.rename(output_path, backup)
        print(f"\n💾 backup เดิม → {backup}")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"✅ บันทึกแล้ว → {output_path}  ({len(result):,} หุ้น, {size_mb:.1f} MB)")
    print(f"\n🌐 เปิดเว็บ:  python -m http.server 8080")
    print(f"   แล้วไปที่:  http://localhost:8080/Us_Surge_Webpage.html")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="รวม filter_universe.json (local) เข้ากับ filter_universe_base.json (base)"
    )
    parser.add_argument("--base",      default=DEFAULT_BASE,   help=f"base file (default: {DEFAULT_BASE})")
    parser.add_argument("--local",     default=DEFAULT_LOCAL,  help=f"local file (default: {DEFAULT_LOCAL})")
    parser.add_argument("--output",    default=DEFAULT_OUTPUT, help=f"output file (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--dry-run",   action="store_true",    help="ดูผลโดยไม่ save")
    parser.add_argument("--no-backup", action="store_true",    help="ไม่ต้อง backup output เดิม")
    parser.add_argument("--quiet",     action="store_true",    help="ไม่แสดง detail ของแต่ละหุ้น")
    args = parser.parse_args()
    run(args)