#!/bin/sh
# This file is executed when starting Ly (before the TTY is taken control of)
# Custom startup code can be placed in this file or the start_cmd var can be pointed to a different file

if [ "$TERM" = "linux" ]; then
	COLORS="0b0b0b f7a692 8ed09c ebb077 bdb3fa f3a3bb 69cee6 dedede 555555 ffd1c0 bfeacd f8d8b3 e1d7ff ffced8 b2e8fa ffffff"

	i=0
	for c in $COLORS; do
		printf "\033]P%x%s" ${i} "${c}"
		i=$(( i + 1 ))
	done

	clear # for fixing background artifacting after changing color
fi
