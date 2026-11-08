#!/bin/sh
# This file is executed when starting Ly (before the TTY is taken control of)
# Custom startup code can be placed in this file or the start_cmd var can be pointed to a different file

# Zen: the console palette from /etc/zen/console.vtrgb (written by "zen apply").
if [ "$TERM" = "linux" ] && [ -r /etc/zen/console.vtrgb ]; then
	i=0
	while read -r c; do
		printf "\033]P%x%s" ${i} "${c#\#}"
		i=$(( i + 1 ))
	done < /etc/zen/console.vtrgb

	clear # for fixing background artifacting after changing color
fi
