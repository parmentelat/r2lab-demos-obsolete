#!/bin/bash
#
# this shell is meant to run inside a dedicated build box
# requirements
# running ubuntu (or at least have debootstrap)
# requires git, rsync, and similar tools, exact list unknown yet
# 
# we run this inside frisbeeimage.pl.sophia.inria.fr - a vivid VM
#
# a /build/ directory
# 
# it is recommended to have /build/fitsophia
# set up as a git clone of
#    https://github.com/parmentelat/fitsophia.git
#
# NOTE about locating proper kernel image
# I could not at first sight figure out the naming scheme in
# the ubuntu repo and pacakges
# Ideally I would have liked to run something like
# apt-get download linux-image
# but this ends in some ghost package that I cannot do anything from
# so to start stuff up I did instead - manually :
# apt-get download linux-image-3.19.0.18-generic
# which was in line with vivid on may 26 2015
# and resulted in this file being downloaded in /build
# linux-image-3.19.0-18-generic_3.19.0-18.18_amd64.deb

COMMAND=$(basename $0 .sh)
LOG=/build/$COMMAND.log

# hard-wired for now
DISTRO=vivid

function init_debootstrap () {
    cd /build
    [ -d $REF ] && { echo reference already present ; return 0; }
    debootstrap -no-gpg-check $DISTRO $REF
    apt-get install rsync
}

# find the most recent deb file installed in /build
function locate_kernel_deb () {
    cd /build
    kerneldeb=$(ls -rt linux-image*.deb | tail -1)
#    [ -z "$kerneldeb" ] && apt-get download linux-image
    [ -z "$kerneldeb" ] && { echo "You need to download some kernel-image deb package"; exit 1; }
    kerneldeb=$(ls -rt linux-image*.deb | tail -1)
    [ -z "$kerneldeb" ] && { echo "Cannot find linux kerneldeb -- exiting"; exit 1; }
#    KERNEL_VER=$(echo $kerneldeb | sed -e s,linux-image_,, -e s,_amd64.deb,,)
    KERNEL_DEB_ABS=/build/$kerneldeb
    KERNEL_DEB_NAME=$kerneldeb
    echo "Using KERNEL deb located in $KERNEL_DEB_ABS" 
}


function clone_and_tweak () {

    cd /build
    [ -d $ROOT ] && { echo "Cleaning up sequels"; rm -rf $ROOT; }

    rsync -a $REF/ $ROOT/

    chroot $ROOT << CHROOT

cat > /etc/fstab << FSTAB
# /etc/fstab: static file system information.
# <file system> <mount point> <type> <options> <dump> <pass>
/dev/ram0 / ext2 defaults 0 0
proc /proc proc defaults 0 1
tmpfs /tmp tmpfs defaults 0 1
FSTAB

cat > /etc/hostname << HOSTNAME
pxefrisbee
HOSTNAME

mkdir -p /etc/network
cat > /etc/network/interfaces << INTERFACES
# Used by ifup(8) and ifdown(8). See the interfaces(5) manpage or
# /usr/share/doc/ifupdown/examples for more information.
# The loopback network interface
auto lo
iface lo inet loopback
# The primary network interface
auto eth0
iface eth0 inet dhcp
INTERFACES

CHROOT

    # kernel
    dpkg-deb -x $KERNEL_DEB_ABS $ROOT/tmp
    # turns out the debootstrap image has no /lib/modules/ directory at all...
    mv $ROOT/tmp/lib $ROOT/modules
    mv -f $ROOT/tmp/boot/vmlinuz* /build/kernel-pxe$DISTRO
    # cleanup
    rm -rf $ROOT/tmp/*
}

function create_entry () {
    ########## telnet /ssh
    # might wish to start with ssh rather than telnet that seems to 
    # pull a lot of dependencies
    ## openssh
    chroot $ROOT apt-get install openssh-server
    # 
    ## telnetld: 
    # create 2 feeds in sources.list.d for 'universe'
    # then apt-get install telnetd
    # xxx not yet implemented
    chroot $ROOT apt-get install telnetd
    #
    echo "XXX FIXME : no entry point (telnet or ssh) yet"
}

function install_newfrisbee () {
    cd frisbee-binaries-inria
    rsync -av frisbee* /$ROOT/usr/sbin
    rsync -av image* /$ROOT/usr/bin
}

function prune_useless_stuff () {
    # xxx this list probably needs more care
    # not sure that we care that much about image size any more in 2015,
    # since uploading 100Mb takes little more than 1s at 500Mbps
    packages="rsyslog adduser initramfs-tools cpio python3 python3-minimal
libnewt0.52 libpcap2 logrotate libpopt0 cron makedev apt apt-utils base-config 
"

    # normalize - remove newlines
    packages=$(echo $packages)
    
    chroot $ROOT << CHROOT
dpkg --purge $packages
CHROOT
}

function wrap_up () {
    cd $ROOT
    find . | cpio -H newc -o | gzip -9 > /build/irfs-pxe$DISTRO.igz    
}

function main () {
    set -x
    REF=/build/$DISTRO-root-ref
    ROOT=/build/$DISTRO-root
    init_debootstrap
    locate_kernel_deb
    clone_and_tweak
    prune_useless_stuff
    install_newfrisbee
    create_entry
    wrap_up
}

main > $LOG 2>&1 
