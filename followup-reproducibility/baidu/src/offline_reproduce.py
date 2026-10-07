"""Offline only: recompute both 96-case panels and their ten-test union."""
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from score_responses import score
from inference import analyze_scored_cells
from holm10_analysis import assemble

def main():
    old = ROOT.parent / "followup"
    cases = json.loads((ROOT / "data/heldout/cases.json").read_text())
    if (old / "data/heldout/cases.json").read_bytes() != (ROOT / "data/heldout/cases.json").read_bytes():
        raise ValueError("Repeated case bank differs")
    old_cells = score("heldout", root=old)
    new_cells = score("heldout", root=ROOT)
    original = analyze_scored_cells(cases, old_cells, ("ds_off", "ds_low", "gpt6_luna_low"), "ds_off", "ds_low")
    fresh = analyze_scored_cells(cases, new_cells, ("ds_off_bd", "ds_low_bd", "gpt6_luna_low"), "ds_off_bd", "ds_low_bd")
    terminal_path = ROOT / "provenance/coreweave-terminal-metadata.json"
    terminal = json.loads(terminal_path.read_text())
    union = assemble(original, fresh, coreweave_terminal_metadata=terminal)
    # The immutable source commitment precedes the public path-free projection.
    union["provenance"]["coreweave_terminal_metadata_canonical_sha256"] = terminal["source_metadata_canonical_sha256"]
    union["provenance"]["public_coreweave_terminal_metadata_sha256"] = hashlib.sha256(terminal_path.read_bytes()).hexdigest()
    destination = ROOT / "results"
    destination.mkdir(exist_ok=True)
    for name, value in (("old-scored-cells", old_cells), ("new-scored-cells", new_cells),
                        ("original-holm4", original), ("new-native-holm4", fresh), ("paper-holm10", union)):
        (destination / (name + ".json")).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"case_clusters_per_endpoint":96,"family_size":10,"luna_endpoint_count":1}))
if __name__ == "__main__": main()
