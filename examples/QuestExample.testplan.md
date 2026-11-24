# Tidewater Errand test plan
run: tidewater-errand-0.1.0
mod: Tidewater Errand
version: 0.1.0
zip: TidewaterErrand-0.1.0.zip

This plan tests Tidewater Errand 0.1.0, a made-up example quest mod. The quest has three stages: stage 10 starts when you first reach a spaceport, stage 20 starts when you read a dockmaster's letter, and stage 30 finishes the quest once you hold 3 Copper. Each stage change writes a `[TWE]` line to the Papyrus log, so the log can prove that a stage was reached. Start with the smoke test; the deep checks try the edge cases.

## Before you start
- Install TidewaterErrand-0.1.0.zip with your mod manager and enable it.
- Turn on Papyrus logging (the mod's README says how), so the log shows the mod's `[TWE]` lines.
- Start a new character, so an old save doesn't hide problems.

## 1 Install and load
- [ ] Start a new game and finish the character creator.
  Expect: no error message about Tidewater Errand.
  smoke: yes
  log: started
- [ ] Before you reach a spaceport, open the console and type `getstage TWE_Quest`.
  Expect: 0, because no stage has been set yet.

## 2 Stage 10: the quest starts
- [ ] Land at a spaceport for the first time.
  Expect: the quest "Tidewater Errand" appears in the Missions menu with the objective "Read the dockmaster's letter".
  smoke: yes
  log: stage-10
- [ ] Type `getstage TWE_Quest` in the console.
  Expect: 10.
  note: If stage 10 never starts, type `setstage TWE_Quest 10` to go on, and mark this group Fail with a note of where you were.

## 3 Stage 20: read the letter
- [ ] Read the letter from your inventory (Inventory > Notes, then Read).
  Expect: the first objective is completed, and "Collect 3 Copper" appears.
  smoke: yes
  log: stage-20
- [ ] Type `getstage TWE_Quest` in the console.
  Expect: 20.
  note: If reading the letter doesn't start stage 20, type `setstage TWE_Quest 20` to go on, and mark this check Fail.

## 4 Stage 30: finish the quest
- [ ] Pick up Copper until you hold 3 (or type `player.additem 00000F3A 3` in the console).
  Expect: the objective "Collect 3 Copper" is completed, and the Missions menu shows "Tidewater Errand" as completed.
  smoke: yes
  log: stage-30
- [ ] Type `getstage TWE_Quest` in the console.
  Expect: 30.

## 5 Edge cases
- [ ] On a second new character, pick up 3 Copper before you land at a spaceport, then read the letter.
  Expect: the quest goes through stage 20 to stage 30 as soon as you read the letter.
  log: stage-30
- [ ] Save at stage 20, quit to the main menu and load the save.
  Expect: the objective is still shown, and collecting the Copper still finishes the quest.
  smoke: yes

## Log checks
After play, run papyrus-log-check on the Papyrus log with the rule file `QuestExample.logrules.json`. Its `order` rule proves that the stages came in the right order. To see the quest's stages in a save, run `sf-save-reader quests <save> --filter Tidewater --details`.

- [ ] The quest script started at the beginning of the game.
  Expect: a `[TWE] started` line.
  log: started
- [ ] The stages came in order: 10, then 20, then 30.
  Expect: the three `[TWE] stage` lines appear in that order, and papyrus-log-check shows `PASS order` for the rule.
  note: An order rule has no id of its own, so `sf-test-plan logs` can't mark this check. Read the report's order line and mark the check yourself.
- [ ] No Papyrus error names a TWE script.
  Expect: no `error:` line that names TWE:ErrandQuestScript.
  log: no-script-errors
