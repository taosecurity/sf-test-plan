@echo off
rem sf-test-plan for Windows: runs sf_test_plan.py next to this file with the Python on PATH.
python -I "%~dp0sf_test_plan.py" %*
