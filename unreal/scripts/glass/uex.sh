# uex.sh <file>  -- run python file in editor, retry while editor is busy (other sessions share it)
cd C:/Users/rtcru/ClaudeProjects/coh-reborn
for t in $(seq 1 30); do
  out=$(python unreal/scripts/ue_exec.py - < "$1" 2>&1)
  if echo "$out" | grep -q "^success"; then echo "$out" | grep -v "^success"; exit 0; fi
  if echo "$out" | grep -q "^FAILED"; then echo "$out" | tail -8; exit 1; fi
  sleep 20
done
echo "editor busy, gave up"; exit 1
