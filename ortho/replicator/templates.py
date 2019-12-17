#!/usr/bin/env python

# template for a script that screens itself
screen_maker = """#!/bin/bash

# note that set -x is too verbose
export SCREEN_LOG=%(screen_log)s
#! is this too recursive?
export BOOTSTRAP_SCRIPT=$(mktemp)

# generate a BASH script that screens itself
cat <<'EOF_OUT'> $BOOTSTRAP_SCRIPT
#!/bin/bash
# run in a screen with specific log file
# typically: TMPDIR="./" tmp_screen_rc=$(mktemp)
echo "[STATUS] temporary screenrc at $tmp_screen_rc"

# ensure that the script screens itself
if [ -z "$STY" ]; then 
echo "[STATUS] executing in a screen"
exec screen -dmS %(screen_name)s -L -Logfile $SCREEN_LOG /bin/bash "$0"
fi
set -e

# clean up the temporary files inside the screened execution
# this must happen before lines with possible errors
# the $tmp_screen_rc serves as a signal that the screen is running
trap "{ rm -f $BOOTSTRAP_SCRIPT $CLEANUP_FILES; }" EXIT ERR

echo "[STATUS] running the following script:"
sed -e 's/^/| /' $BOOTSTRAP_SCRIPT
echo "[STATUS] end of script"
echo "[STATUS] start time $(date)"

# prelim%(prelim)s

# KERNEL
%(contents)s

# post%(post)s

echo "[STATUS] end time $(date)"

# end of the screen
EOF_OUT

# run the script which screens itself
bash $BOOTSTRAP_SCRIPT
"""
