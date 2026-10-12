"""usage: python run.py <script.py> [KEY=VALUE ...]  -- runs a step inside the open editor"""
import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
script = os.path.abspath(sys.argv[1])
env = dict(a.split("=", 1) for a in sys.argv[2:])
# the editor's Python process lives on between runs: drop flags from earlier runs
code = "import os, sys\nfor _m in ('reborn_common', 'build_pcg'): sys.modules.pop(_m, None)  # pick up edits\nfor _k in [k for k in os.environ if k.startswith('REBORN_')]: del os.environ[_k]\n" + "".join("os.environ[%r]=%r\n" % kv for kv in env.items()) + \
    "exec(compile(open(%r).read(), %r, 'exec'), {'__file__': %r, '__name__': '__main__'})\n" % (script, script, script)
ue = os.path.join(here, "..", "..", "..", "unreal", "scripts", "ue_exec.py")
p = subprocess.run([sys.executable, ue, "-"], input=code, text=True)
sys.exit(p.returncode)
