#!/bin/sh
OCD_CFG_FILE="$(mktemp /tmp/.openocd_cfg.XXXXX)"
OCD_PID=""
LOGFILE="$(mktemp /tmp/.openocd_log.XXXXX)"
LOGFILE_CMD="$(mktemp /tmp/.openocd_log_cmd.XXXXX)"

openocd_create_cfg_file () {
	cat > "${OCD_CFG_FILE}" << END
source [find interface/imx-native.cfg]

transport select swd

set WORKAREASIZE 0

source [find target/nrf52.cfg]

imx_gpio_swd_nums ${OCD_SWD_NUMS}
END
}

openocd_cmd () {
	cmd="${1}"

	echo -n "$(date): " >> "${LOGFILE_CMD}" 2>&1
	echo "${cmd}" | nc localhost 4444 | tr -d '\000' >> "${LOGFILE_CMD}" 2>&1
	echo "" >> "${LOGFILE}" 2>&1
}

openocd_check_busy_state () {
	echo "Checking chip state"
	OCD_PID=$(openocd -f "${OCD_CFG_FILE}" -c init >> "${LOGFILE}" 2>&1 & echo ${!})
	sleep 1
	grep -q "telnet" "${LOGFILE}"
	result="${?}"
	if [ "${result}" != "0" ]; then
		echo "Chip is busy! Please power cycle and run again."
		cleanup
		exit 1
	fi
}

openocd_check_state () {
	result=$(echo "targets" | nc localhost 4444 | tr -d '\000')
	if echo "${result}" | grep -q halted; then
		echo "Chip is ready for flashing, continuing..."
	elif echo "${result}" | grep -q running; then
		echo "Chip is running, halting..."
		openocd_cmd "halt"
	elif echo "${result}" | grep -q unknown; then
		echo "Chip is locked! Unlocking and preparing for flashing..."

		# Turn on ERASEALL bit
		openocd_cmd "nrf52.dap apreg 1 0x04 0x00"
		openocd_cmd "nrf52.dap apreg 1 0x04 0x01"
		sleep 1

		# Reset chip
		openocd_cmd "nrf52.dap apreg 1 0x00 0x01"
		openocd_cmd "nrf52.dap apreg 1 0x00 0x00"

		# Turn off ERASEALL bit
		openocd_cmd "nrf52.dap apreg 1 0x04 0x00"
		
		# Undergo reset and halt chip
		openocd_cmd "reset"
		openocd_cmd "halt"
	else
		echo "Chip is in unknown state, canceling."
		openocd_cmd "shutdown"
		exit 1
	fi
}

openocd_load () {
	echo "Programming flash."
	openocd_cmd "init"
	openocd_cmd "reset halt"
	openocd_cmd "flash write_image erase ${FILENAME} ${FLASH_OFFSET}"
}

openocd_reset_run () {
	openocd_cmd "reset run"
}

openocd_shutdown () {
	openocd_cmd "shutdown"
	sleep 1
}

cleanup () {
	if [ -f "${OCD_CFG_FILE}" ]; then
		rm -f "${OCD_CFG_FILE}"
	fi
	pid="$(pgrep openocd)"
	if [ -n "${pid}" ]; then
		if [ "${pid}" != "${OCD_PID}" ]; then
			echo "Warning.  Detecting a running openocd that was not started by me, pid: <${pid}>"
		else
			echo "Killing running openocd pid: <${OCD_PID}>, detected pid: <${pid}>"
			pkill "${OCD_PID}" >> "${LOGFILE}" 2>&1
			pkill -9 "${OCD_PID}" >> "${LOGFILE}" 2>&1
		fi
	fi
}

usage () {
	echo "$(basename "${0}"): -s|--sink <sink: 1|2> -t|--type <type: boot|program> <FILE>"
	echo ""
	echo "	example: $(basename "${0}") -s1 -tboot boot.bin.elf"
	exit 1
}

options=$(getopt -l "sink::,type::" -o ":s::t::" -- "${@}")
eval set -- "${options}"

while true
do
	case ${1} in
		-s|--sink )
			shift
			if [ "${1}" = "1" ]; then
				OCD_SWD_NUMS="82 81"
			elif [ "${1}" = "2" ]; then
				OCD_SWD_NUMS="59 125"
			else
				usage
				exit 1
			fi
			;;
		-t|--type )
			shift
			if [ "${1}" = "boot" ]; then
				FLASH_OFFSET="0x0"
			elif [ "${1}" = "program" ]; then
				FLASH_OFFSET="0x8000"
			else
				usage
				exit 1
			fi
			;;
		\? )
			usage
			;;
		: )
			echo "Invalid option: ${OPTARG} requires an argument" 1>&2
			;;
		-- )
			shift
			break
			;;
		* )
			usage
			;;
	esac
	shift
done

if [ "${#}" -ne "1" ]; then
	usage
else
	FILENAME="${1}"
	if [ -f "${FILENAME}" ]; then
		touch "${LOGFILE}"
		openocd_create_cfg_file
		openocd_check_busy_state
		openocd_check_state
		openocd_load
		openocd_reset_run
		openocd_shutdown
		cleanup
		echo "All done!"
	else
		echo "The <${FILENAME}> does not exist!"
		exit 1
	fi
fi
