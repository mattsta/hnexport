"""Data validation and integrity checking."""

import json
import lzma
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..logger import logger


@dataclass
class ValidationReport:
    """Data validation report."""

    total_bundles: int = 0
    valid_bundles: int = 0
    corrupt_bundles: List[str] = field(default_factory=list)
    malformed_bundles: List[Tuple[str, str]] = field(default_factory=list)
    missing_ids: Set[int] = field(default_factory=set)
    duplicate_ids: Set[int] = field(default_factory=set)
    total_items: int = 0
    valid_items: int = 0
    invalid_items: int = 0
    schema_errors: Dict[str, int] = field(default_factory=dict)
    bundle_range_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert report to dictionary."""
        return {
            "total_bundles": self.total_bundles,
            "valid_bundles": self.valid_bundles,
            "corrupt_bundles": self.corrupt_bundles,
            "malformed_bundles": self.malformed_bundles,
            "missing_ids": sorted(list(self.missing_ids))[:100],  # Limit for display
            "missing_ids_count": len(self.missing_ids),
            "duplicate_ids": sorted(list(self.duplicate_ids))[:100],
            "duplicate_ids_count": len(self.duplicate_ids),
            "total_items": self.total_items,
            "valid_items": self.valid_items,
            "invalid_items": self.invalid_items,
            "schema_errors": self.schema_errors,
            "bundle_range_errors": self.bundle_range_errors,
        }

    def __str__(self) -> str:
        """Human-readable report."""
        lines = [
            "=" * 60,
            "Data Validation Report",
            "=" * 60,
            "",
            f"Bundles:      {self.valid_bundles:,}/{self.total_bundles:,} valid",
            f"Items:        {self.valid_items:,}/{self.total_items:,} valid",
            f"Corrupt:      {len(self.corrupt_bundles):,} bundles",
            f"Duplicates:   {len(self.duplicate_ids):,} items",
            f"Missing IDs:  {len(self.missing_ids):,} items",
        ]

        if self.schema_errors:
            lines.append("")
            lines.append("Schema Errors:")
            for error_type, count in sorted(self.schema_errors.items()):
                lines.append(f"  {error_type}: {count:,}")

        if self.bundle_range_errors:
            lines.append("")
            lines.append(f"Bundle Range Errors: {len(self.bundle_range_errors)}")

        return "\n".join(lines)


class DataValidator:
    """Validate downloaded HackerNews data integrity.

    Checks for corruption, missing items, and data consistency.

    Example:
        validator = DataValidator(data_dir=Path("hn/item"))
        report = validator.validate()
        if report.corrupt_bundles:
            print(f"Found {len(report.corrupt_bundles)} corrupt bundles")
    """

    # Required fields for each item type
    REQUIRED_FIELDS = {
        "story": ["id", "type", "by", "time", "title"],
        "comment": ["id", "type", "by", "time", "text"],
        "job": ["id", "type", "time", "title"],
        "poll": ["id", "type", "by", "time", "title"],
        "pollopt": ["id", "type", "parent"],
    }

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.item_dir = data_dir / "item" if (data_dir / "item").exists() else data_dir

    def validate(
        self,
        check_gaps: bool = False,
        check_schema: bool = True,
        check_ranges: bool = True,
        progress_callback: Optional[callable] = None,
    ) -> ValidationReport:
        """Validate all bundles.

        Args:
            check_gaps: Check for missing IDs in sequence
            check_schema: Validate item schemas
            check_ranges: Validate bundle filename ranges match contents
            progress_callback: Optional callback(current, total) for progress

        Returns:
            ValidationReport with validation results
        """
        report = ValidationReport()
        seen_ids: Set[int] = set()
        all_ids: List[int] = []

        bundles = sorted(self.item_dir.glob("*.xz"))
        report.total_bundles = len(bundles)

        logger.info(f"Validating {len(bundles):,} bundles...")

        for idx, bundle_path in enumerate(bundles):
            if progress_callback and idx % 100 == 0:
                progress_callback(idx, report.total_bundles)

            bundle_name = bundle_path.name

            # Validate bundle
            try:
                bundle_ids = self._validate_bundle(
                    bundle_path, report, seen_ids, check_schema, check_ranges
                )
                all_ids.extend(bundle_ids)
                report.valid_bundles += 1

            except lzma.LZMAError as e:
                logger.error(f"Corrupt bundle (LZMA): {bundle_name} - {e}")
                report.corrupt_bundles.append(bundle_name)
            except Exception as e:
                logger.error(f"Error validating bundle: {bundle_name} - {e}")
                report.malformed_bundles.append((bundle_name, str(e)))

        if progress_callback:
            progress_callback(report.total_bundles, report.total_bundles)

        # Check for gaps if requested
        if check_gaps and all_ids:
            all_ids.sort()
            report.missing_ids = self._find_missing_ids(all_ids)

        logger.info(
            f"Validation complete: {report.valid_bundles}/{report.total_bundles} bundles valid, "
            f"{report.valid_items:,} items, {len(report.duplicate_ids)} duplicates"
        )

        return report

    def _validate_bundle(
        self,
        bundle_path: Path,
        report: ValidationReport,
        seen_ids: Set[int],
        check_schema: bool,
        check_ranges: bool,
    ) -> List[int]:
        """Validate a single bundle.

        Returns:
            List of item IDs found in bundle
        """
        bundle_name = bundle_path.name
        bundle_ids: List[int] = []

        # Parse bundle filename to get expected range
        expected_range = self._parse_bundle_range(bundle_name)

        with lzma.open(bundle_path, "rt", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue

                # Handle null items
                if line.strip() == "null":
                    report.total_items += 1
                    continue

                try:
                    item = json.loads(line)
                except json.JSONDecodeError as e:
                    logger.warning(
                        f"Invalid JSON in {bundle_name} line {line_num}: {e}"
                    )
                    report.invalid_items += 1
                    report.total_items += 1
                    continue

                report.total_items += 1

                # Validate item
                item_id = item.get("id")
                if not item_id or not isinstance(item_id, int):
                    report.schema_errors["missing_or_invalid_id"] = (
                        report.schema_errors.get("missing_or_invalid_id", 0) + 1
                    )
                    report.invalid_items += 1
                    continue

                # Check for duplicates
                if item_id in seen_ids:
                    report.duplicate_ids.add(item_id)
                    logger.debug(f"Duplicate ID {item_id} in {bundle_name}")

                seen_ids.add(item_id)
                bundle_ids.append(item_id)

                # Check if ID is in expected range
                if check_ranges and expected_range:
                    start, end = expected_range
                    if not (start <= item_id <= end):
                        error_msg = (
                            f"{bundle_name}: Item {item_id} outside range {start}-{end}"
                        )
                        if error_msg not in report.bundle_range_errors:
                            report.bundle_range_errors.append(error_msg)
                            logger.warning(error_msg)

                # Schema validation
                if check_schema:
                    self._validate_item_schema(item, report)

                report.valid_items += 1

        return bundle_ids

    def _validate_item_schema(self, item: Dict, report: ValidationReport) -> None:
        """Validate item has required fields for its type."""
        item_type = item.get("type")

        if not item_type:
            report.schema_errors["missing_type"] = (
                report.schema_errors.get("missing_type", 0) + 1
            )
            return

        # Check required fields for this type
        required_fields = self.REQUIRED_FIELDS.get(item_type, [])

        for field in required_fields:
            # Skip 'by' field if item is deleted (deleted items have no author)
            if field == "by" and (item.get("deleted") or item.get("dead")):
                continue

            if field not in item or item[field] is None:
                error_key = f"missing_{field}_in_{item_type}"
                report.schema_errors[error_key] = (
                    report.schema_errors.get(error_key, 0) + 1
                )

    def _parse_bundle_range(self, bundle_name: str) -> Optional[Tuple[int, int]]:
        """Parse bundle filename to extract ID range.

        Args:
            bundle_name: Bundle filename (e.g., "0-99.xz")

        Returns:
            Tuple of (start_id, end_id) or None if can't parse
        """
        # Match patterns like "0-99.xz" or "100-199.xz"
        match = re.match(r"(\d+)-(\d+)\.xz$", bundle_name)
        if match:
            start = int(match.group(1))
            end = int(match.group(2))
            return (start, end)
        return None

    def _find_missing_ids(self, sorted_ids: List[int]) -> Set[int]:
        """Find missing IDs in sequence.

        Args:
            sorted_ids: Sorted list of item IDs

        Returns:
            Set of missing IDs
        """
        if not sorted_ids or len(sorted_ids) < 2:
            return set()

        missing = set()
        min_id = sorted_ids[0]
        max_id = sorted_ids[-1]

        # Only check for gaps, don't report every missing ID from 1 to max
        # This would be too many for HN data
        logger.info(f"Checking for gaps in range {min_id:,} to {max_id:,}")

        # Convert to set for O(1) lookup
        id_set = set(sorted_ids)

        # Sample check: look for missing IDs in reasonable ranges
        # For full HN dataset, we can't check every ID
        for i in range(len(sorted_ids) - 1):
            current_id = sorted_ids[i]
            next_id = sorted_ids[i + 1]

            # If gap is small (< 1000), check each ID
            gap_size = next_id - current_id
            if 1 < gap_size < 1000:
                for check_id in range(current_id + 1, next_id):
                    if check_id not in id_set:
                        missing.add(check_id)

        logger.info(f"Found {len(missing):,} missing IDs in gaps")
        return missing

    def validate_bundle_file(self, bundle_path: Path) -> Tuple[bool, Optional[str]]:
        """Validate a single bundle file.

        Args:
            bundle_path: Path to bundle file

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            with lzma.open(bundle_path, "rt", encoding="utf-8") as f:
                line_count = 0
                for line in f:
                    if line.strip() and line.strip() != "null":
                        try:
                            item = json.loads(line)
                            if not item.get("id"):
                                return (False, "Item missing ID field")
                        except json.JSONDecodeError as e:
                            return (False, f"Invalid JSON: {e}")
                    line_count += 1

                if line_count == 0:
                    return (False, "Empty bundle")

            return (True, None)

        except lzma.LZMAError as e:
            return (False, f"LZMA decompression error: {e}")
        except Exception as e:
            return (False, f"Unexpected error: {e}")
