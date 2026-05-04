import sys
import site
import importlib.util

print(sys.executable)
print(site.getusersitepackages())
print(importlib.util.find_spec("pytest"))
