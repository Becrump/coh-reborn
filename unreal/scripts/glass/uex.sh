# uex.sh <file> -- run a python file in the editor.
# Retries ONLY when the editor could not be reached before the command was sent.
# Never re-sends a command that may already have run (a lost connection mid-command can be a crash:
# on 2026-10-21 blind retries re-ran a crashing export three times across editor restarts).
cd C:/Users/rtcru/ClaudeProjects/coh-reborn
for t in $(seq 1 10); do
  out=$(python unreal/scripts/ue_exec.py - < "$1" 2>&1)
  if echo "$out" | grep -q "^success"; then echo "$out" | grep -v "^success"; exit 0; fi
  if echo "$out" | grep -q "no Unreal editor found\|failed to attempt the command socket"; then sleep 20; continue; fi
  echo "$out" | tail -8; echo "NOT RETRIED (command may have run or crashed the editor)"; exit 1
done
echo "editor unreachable, gave up"; exit 1
