# Beacon Mod test plan
run: beacon-0.1.0
mod: Beacon Mod
version: 0.1.0
zip: BeaconMod-0.1.0.zip

This plan tests Beacon Mod 0.1.0, a made-up example mod that gives you a placeable beacon. Start with the smoke test; the deep checks are for before a public release.

## Before you start
- Install BeaconMod-0.1.0.zip with your mod manager and enable it.
- Turn on Papyrus logging (the mod's README says how), so `sf-test-plan logs` can check the log lines.

## 1 Install and load
These checks prove the mod loads.

- [ ] Start a new game and finish the character creator.
  Expect: no error message about Beacon Mod.
  smoke: yes
  log: loaded
- [ ] Open **Settings > Gameplay**.
  Expect: a "Beacon" group with "Show Debug Messages (PC only)", off by default.
  smoke: yes

## 2 Main feature
- [ ] Open the console and type `player.additem 0001A2B3 1`.
  Expect: one Beacon in your inventory.
  smoke: yes
- [ ] Drop the beacon and activate it.
  Expect: the message "Beacon placed." and a light on the ground.
  smoke: yes
  log: placed
- [ ] Pick the beacon up again.
  Expect: it goes back to your inventory.
  note: Try it in a building too; [the mod page](https://example.com/beacon) says it works indoors.

## 3 Save and load
- [ ] Save, quit to the main menu and load the save.
  Expect: a placed beacon is still there.
  smoke: yes
  log: restored
