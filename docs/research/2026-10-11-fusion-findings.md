# Fusion reverse-engineering findings

Date: 2026-10-11. Status: initial static investigation, not full reverse engineering or a rebuilt app.

## Reference identity

The installed application is Autodesk Fusion 2705.1.15 (com.autodesk.fusion360).
Source bundle: /Users/ivanchen/Library/Application Support/Autodesk/webdeploy/production/4fcc3ec853a7fe76514fe04cc5fd7741e6b2c4ff/Autodesk Fusion.app.

The application in ~/Applications is a small launcher; inspection used the real application bundle. Its universal executable contains x86_64 and ARM64 slices. A copied ARM64 slice was derived with lipo for Ghidra admission. The installed application was not modified or launched by this investigation.

## Evidence ledger

| ID | Observation | Evidence type | Limits |
|---|---|---|---|
| F01 | Bundle identity and version above | Parsed Info.plist | Installed metadata; not proof of feature access |
| F02 | About 11 GB; 98,365 regular non-symlink files; 1,357 .dylib/.so files | Bounded filesystem inventory of Contents | Dependencies and duplicates inflate counts |
| F03 | Qt framework and Autodesk Neutron library loads | REA inspect_macho | Dependency metadata only; referenced libraries were not all resolved or analyzed |
| F04 | 1,142 declaration records; 1,084 distinct command IDs across 32 selected XML files | Inert XML parsing; zero parse errors | Incomplete command census; includes repeated declarations |
| F05 | core 369, fusion 1,051, cam 358 API classes | Python AST parsing, no execution | API declarations are not recovered algorithms |
| F06 | Entrypoint creates application, initializes startup services and handles startup conditions | Ghidra pseudocode with readable imported function names | Static interpretation, not runtime observation |
| F07 | Two selected CAM command XML files are empty | XML parsing | Does not establish CAM has no commands; another discovery method is needed |
| F08 | Main-name procedure search returned no matches | REA search_procedures, bounded literal search | Does not establish absence of program entry or feature code |

REA Mach-O evidence:
- ID: ev_f505377566723ef0e039b67248b5a3f145df91aa6682f0f0d8f48d56dd2bf9db.
- ARM64 slice SHA-256: 5ff10bba6bd636a9cf6882205636978051348cb7e4b1dadee06fb9fb12e16daf.
- Operation: inspect_macho, native-macos provider.

Entrypoint decompilation:
- ID: ev_cc9a834569e4583573c27da8cde396b0bf6ecbdcdbb78451ec9de97af20e1c95.
- Ghidra 12.1.4, procedure_pseudo_code.
- Entrypoint address: 0x100010d44, derived from LC_MAIN file offset mapped through its segment.
- About 11,471 characters of recovered pseudocode retained privately on the mini.
- No original modeling source or complete application source was recovered.

## Declaration counts

| Packaged application grouping | Declaration records |
|---|---:|
| Fusion | 419 |
| Simulation | 361 |
| FusionDoc | 155 |
| Electron (the packaged electronics module name) | 154 |
| ParaMesh | 33 |
| Animation | 13 |
| VolumetricField | 7 |
| Total | 1,142 |

The name Electron here is a package path, not evidence that Fusion is an Electron web application.

## Interpretation

The executable is a startup entry into a much larger modular product. The evidence supports multiple packaged UI/domain systems and a broad exposed API. It does not establish their internal algorithms or completeness of a future recreation.

The next valuable reverse-engineering work is a set of reference workflows with inputs, outputs and measured behavior, followed by focused investigation of unresolved questions. Bulk decompilation of the entire bundle would produce a large body of uncertain output without itself providing a validated implementation.

## Reproducibility and artifact locations

SSD research root: /Volumes/SamsungSSD1/tools/rea/work/fusion-2705.1.15.
- artifacts/: copied main executable, derived ARM64 slice and Info.plist.
- package-metadata/: 35 selected XML/Python API files, approximately 12.3 MB.
- evidence/metadata-source-manifest.json: source-relative paths, sizes and SHA-256 hashes.
- evidence/main-arm64-macho.json: REA metadata evidence.
- evidence/entrypoint-decompile.json: REA pseudocode evidence.
- evidence/command-inventory.csv: declaration identifiers, module/source and explicit unimplemented/unverified states.
- evidence/api-class-inventory.json: class names and method counts.
- evidence/inventory-summary.json: counts and parsing scope.

The accompanying CSV is a discovery artifact. Every entry starts not-implemented and behavior-unverified. It is not a feature checklist proven complete.
