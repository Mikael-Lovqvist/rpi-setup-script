#   ___ ___  _  _ ___ ___ ___
#  / __/ _ \| \| | __|_ _/ __|
# | (_| (_) | .` | _| | | (_ |
#  \___\___/|_|\_|_| |___\___|

#Local directories
download_dir = 'downloads'
mount_dir = 'mounts'

#Target configuration
rpi_major_model = 4
device = '/dev/sde'
boot_dir = 'boot'
boot_size = '512M'
min_boot_size = 512 << 20	#512M

#First time setup settings
first_time_setup_actions = [
	#Commands can be copy or symlink
	#Arguments that are prefixed with L: or T: will be resolved to local or target files relative to mount_dir
	['copy', 		'L:payloads/first-time-setup.service',					'T:/etc/systemd/system/first-time-setup.service'],
	['copy', 		'L:payloads/first-time-setup.sh', 						'T:/usr/local/bin/first-time-setup.sh'],
	['chmod', 		'+x', 													'T:/usr/local/bin/first-time-setup.sh'],
	['symlink', 	'T:/etc/systemd/system/first-time-setup.service', 		'T:/etc/systemd/system/multi-user.target.wants/'],
]

#Downloads
tarball_download = 'http://os.archlinuxarm.org/os/ArchLinuxARM-rpi-aarch64-latest.tar.gz'



# END OF CONFIG




# Based on https://archlinuxarm.org/platforms/armv8/broadcom/raspberry-pi-4 for AArch64

# NOTES
# 	Note 1
#		This will fail if there are not exactly one .tar.gz in the directory which is by design.
#		We could get in trouble if we have a .tar.gz but download turns into some other filename.
#		Best would have been if wget could have output a list of files it wrote but that is not a feature of wget.


import subprocess, json, re, tempfile
from pathlib import Path

download_path = Path(download_dir)
mount_path = Path(mount_dir)
boot_path = Path(mount_dir) / boot_dir


def user_program(command, *positional, **named):
	return subprocess.run(command, *positional, **named)

def su_program(command, *positional, **named):
	return subprocess.run(('sudo', *command), *positional, **named)


def do_ensure_proper_partition_table():
	partition_setup_script = f'''
	label: dos

	: size={boot_size}, type=c
	: type=83
	'''

	result = su_program(('sfdisk', '--json', device), check=True, capture_output=True, text=True, encoding='utf-8')
	partition_table = json.loads(result.stdout)['partitiontable']

	assert partition_table['unit'] == 'sectors'
	sector_size = partition_table['sectorsize']

	repartition = True
	if 'partitions' in partition_table and len(partition_table['partitions']) > 1:
		first_part_size = partition_table['partitions'][0]['size'] * sector_size

		if first_part_size >= min_boot_size:
			repartition = False

	if repartition:
		print('Repartition required')
		su_program(('sfdisk', device), check=True, input=partition_setup_script, text=True, encoding='utf-8')
	else:
		print('Partition table seems fine')


def do_create_file_systems():
	su_program(('mkfs.vfat', f'{device}1'), check=True)
	su_program(('mkfs.ext4', f'{device}2'), check=True)


def do_download_files():
	download_path.mkdir(parents=True, exist_ok=True)
	user_program(('wget', '--timestamping', tarball_download), check=True, cwd=bytes(download_path))


def do_mount_filesystems():
	mount_path.mkdir(parents=True, exist_ok=True)
	su_program(('mount', f'{device}2', bytes(mount_path)), check=True)
	su_program(('mkdir', '-p', bytes(boot_path)), check=True)
	su_program(('mount', f'{device}1', bytes(boot_path)), check=True)


def do_extract_file_system(tar_gz_file):
	su_program(('bsdtar', '-xpf', bytes(Path(tar_gz_file)), '-C', bytes(mount_path)), check=True)

def do_update_fstab():
	if rpi_major_model == 4:
		fstab_path = mount_path / 'etc/fstab'
		partition_pattern = re.compile(r'^(\s*)/dev/mmcblk(\d+)p(\d+)', re.M)

		def update_function(match):
			[whitespace, device_id, partition_id] = match.groups()
			device_id = 1	# update device id for rpi4
			return f'{whitespace}/dev/mmcblk{device_id}p{partition_id}'

		print('Updating fstab')
		with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=True, delete_on_close=False) as temp_file:
			temp_file.write(partition_pattern.sub(update_function, fstab_path.read_text()))
			temp_file.close()
			su_program(('cp', temp_file.name, bytes(fstab_path)), check=True)
	else:
		print('No update is required')


def	do_install_first_time_setup():

	def translate_argument(argument):

		match argument.partition(':'):
			case ['L', ':', path]:
				return path

			case ['T', ':', path]:
				return bytes(mount_path / Path(path).relative_to('/'))

		return argument


	for entry in first_time_setup_actions:
		match entry:
			case ['copy', *arguments]:
				su_program(('cp', *map(translate_argument, arguments)), check=True)

			case ['chmod', *arguments]:
				su_program(('chmod', *map(translate_argument, arguments)), check=True)

			case ['symlink', *arguments]:
				su_program(('ln', '-s', *map(translate_argument, arguments)), check=True)

			case _:
				raise Exception(entry)

def do_unmount_file_systems():
	mount_path.mkdir(parents=True, exist_ok=True)
	su_program(('umount', bytes(boot_path)), check=True)
	su_program(('umount', bytes(mount_path)), check=True)

def do_eject_device():
	su_program(('eject', device), check=True)


def do_all_the_things(check_partition_tables=True, create_file_systems=True, download_files=True, verify_downloaded_file_exists=True, mount_file_systems=True, extract_files=True, update_fstab=True, install_first_time_setup=True, unmount_file_systems=True, eject_device=True):
	#Check requirements
	if extract_files:
		assert verify_downloaded_file_exists

	#Do the things
	if check_partition_tables:
		print('Checking partition tables')
		do_ensure_proper_partition_table()

	if create_file_systems:
		print('Creating file systems')
		do_create_file_systems()

	if download_files:
		print('Downloading files')
		do_download_files()

	if verify_downloaded_file_exists:
		[tar_gz_file] = download_path.glob('*.tar.gz')	# Note 1

	if mount_file_systems:
		print('Mounting file systems')
		do_mount_filesystems()

	if extract_files:
		print('Extracting files')
		do_extract_file_system(tar_gz_file)

	if update_fstab:
		print('Update fstab if needed')
		do_update_fstab()

	if install_first_time_setup:
		print('Installing first time setup scripts')
		do_install_first_time_setup()

	if unmount_file_systems:
		print('Synchronizing and unmounting file systems')
		do_unmount_file_systems()

	if eject_device:
		print('Ejecting device')
		do_eject_device()

# For being Selective:

# do_all_the_things(
# 	check_partition_tables=False,
# 	create_file_systems=False,
# 	download_files=False,
# 	verify_downloaded_file_exists=False,
# 	mount_file_systems=False,
# 	extract_files=False,
# 	update_fstab=False,
# 	install_first_time_setup=False,
# 	unmount_file_systems=False,
# 	eject_device=False,
# )

# For doing all the things
raise Exception('Make sure you have set things up properly before running this! Check that it is the proper device and comment out this line when you are confident you are not wrecking havoc on your system.')
do_all_the_things()

