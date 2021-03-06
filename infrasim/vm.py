#!/usr/bin/env python
# -*- coding: utf-8 -*-

import jinja2, uuid, cfgparse, subprocess, os
import libvirt, logging
import random

VM_DEFAULT_CONFIG = "/etc/infrasim/infrasim.conf"
VM_DEFAULT_XML = "/usr/local/etc/infrasim/vnode.xml"
MAX_QEMU_MAC_NUM=8

class VM:
    def __init__(self):
        self.node = {"name": "quanta_d51", "uuid": str(uuid.uuid1()),
                     "bios": {}, "virtual_type": "qemu", "mem_size": 512,
                     "vcpu_num": 4, "vcpu_type": "Haswell"}
        self.render_xml = ""
        self.logger = logging.getLogger('infrasim')
        self.set_virtual_type()
        self.set_bios_data(self.node["name"])
        self.set_sata_disks_with_size(1, 4, False)
        self.set_network("nat", None)
        if os.path.exists(os.environ['HOME'] + '/.infrasim') is False:
            os.mkdir(os.environ['HOME'] + "/.infrasim")

    def set_virtual_type(self):
        output = subprocess.check_output("cat /proc/cpuinfo".split(" "))
        if output.find("vmx") > 0:
            self.node["virtual_type"] = "kvm"

    def set_bios_data(self, node):
        bios = {"bios": {}, "system": {}, "base": {}}
        bios_file = "/usr/local/etc/infrasim/{0}/{0}_smbios.bin".format(node)
        bios["bios"]["vendor"] = subprocess.check_output(
            "dmidecode --from-dump {0} -s bios-vendor".format(bios_file).split(" "))
        bios["system"]["manufacturer"] = subprocess.check_output(
            "dmidecode --from-dump {0} -s system-manufacturer".format(bios_file).split(" "))
        bios["system"]["product"] = subprocess.check_output(
            "dmidecode --from-dump {0} -s system-product-name".format(bios_file).split(" "))
        bios["system"]["version"] = subprocess.check_output(
            "dmidecode --from-dump {0} -s system-version".format(bios_file).split(" "))
        bios["base"]["manufacturer"] = subprocess.check_output(
            "dmidecode --from-dump {0} -s baseboard-manufacturer".format(bios_file).split(" "))
        bios["base"]["product"] = subprocess.check_output(
            "dmidecode --from-dump {0} -s baseboard-product-name".format(bios_file).split(" "))
        bios["base"]["version"] = subprocess.check_output(
            "dmidecode --from-dump {0} -s baseboard-version".format(bios_file).split(" "))
        bios["base"]["serial"] = subprocess.check_output(
            "dmidecode --from-dump {0} -s baseboard-serial-number".format(bios_file).split(" "))
        self.node["bios"] = bios

    def set_memory_size(self, mem_size=512):
        self.node["mem_size"] = mem_size

    def set_vcpu_num(self, vcpu_num=4):
        self.node["vcpu_num"] = vcpu_num

    def set_vcpu_type(self):
        self.node["vcpu_type"] = "Haswell"

    def set_pxe(self):
        self.node["pxe"] = "{0}\n{1}\n{2}\n".format(
            "<kernel>/var/www/html/CentOS/7.0/images/pxeboot/vmlinuz</kernel>",
            "<initrd>/var/www/html/CentOS/7.0/images/pxeboot/initrd.img</initrd>",
            "<cmdline>ks=http://192.168.191.133/kickstart/centos-ks.cfg</cmdline>")

    def create_disk_image(self, disk_idx, disk_size=4, force=True):
        disk_dir = os.environ['HOME'] + "/.infrasim"
        disk_img = "sd{0}.img".format(chr(97+disk_idx))
        if os.path.isfile(disk_dir + disk_img):
            if not force:
                return

            image_size = subprocess.check_output("qemu-img info {} | grep 'virtual size'".format(disk_dir+disk_img), shell=True)
            image_size = float(image_size.split()[2][:-1].strip())
            if image_size != float(disk_size):
                os.remove(disk_dir + disk_img)
            else:
                return
        command = "qemu-img create -f qcow2 {0}{1} {2}G".format(disk_dir, disk_img, disk_size)
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
        process.communicate()

    def set_sata_disks_with_size(self, disk_num=1, disk_size=4, force=True):
        disk_dir = os.environ['HOME'] + "/.infrasim"
        disks = []
        for i in range(0, disk_num):
            self.create_disk_image(i, disk_size, force)
            disk = {"file": "{0}sd{1}.img".format(disk_dir, chr(97+i)),
                    "dev": "sd" + chr(97+i), "name": "sata0-0-" + str(i)}
            disks.append(disk)
        self.node["disks"] = disks

    def mac_generator(self):
        return ':'.join(map(lambda x: "%02x" % x, [0x00, 0x16, 0x3e,
            random.randint(0x00, 0x7f),
            random.randint(0x00, 0xff),
            random.randint(0x00, 0xff)]))

    def set_network(self, mode, name):
        nets = []
        change_flag = False

        conf = cfgparse.ConfigParser()
        f = conf.add_file(VM_DEFAULT_CONFIG, type = 'ini')
        conf.parse()

        # add existing options into config parser
        if self.has_option(conf, "node", "qemu_mac_num") is True:
            conf.add_option("qemu_mac_num", keys="node")

        mac_list = []
        for i in range(0, MAX_QEMU_MAC_NUM):
            if self.has_option(conf, "node", "qemu_mac"+str(i)) is True:
                mac_list.append(conf.add_option("qemu_mac"+str(i), keys="node"))

        # parse valid options
        opts = conf.parse()

        #set mac number
        if self.has_option(conf, "node", "qemu_mac_num") is True:
            mac_num = opts.qemu_mac_num
        else:
            mac_num = 1

        #set netmode in vnode.xml
        if mode == "nat":
            self.node["netmode"] = "nat"
        else:
            self.node["netmode"] = "bridge"

        #set mac address
        for i in range(0,int(mac_num)):
            #init mac, read mac from config or generate random mac
            mac = "null"
            if self.has_option(conf, "node", "qemu_mac"+str(i)) is True:
                mac = mac_list[i].get()
                if mac == "null":
                    mac = self.mac_generator()
                    f.set_option("qemu_mac"+str(i), mac, "node")
                    change_flag = True
            else:
                mac = self.mac_generator()
                f.set_option("qemu_mac"+str(i), mac, "node")
                change_flag = True

            #append mac in nets for "nat" and "bridge" mode
            if mode == "nat":
                nets.append({"mac":mac})
            else:
                tap = "macvtap"+str(i)
                nets.append({"mac":mac, "dev":name, "tap":tap})

        for i in range(int(mac_num), MAX_QEMU_MAC_NUM):
            #set mac to null
            mac = "null"
            if self.has_option(conf,"node", "qemu_mac"+str(i)) is True:
                mac = mac_list[i].get()
                if mac != "null":
                    mac = "null"
                    f.set_option("qemu_mac"+str(i), mac, "node")
                    change_flag = True

        if (change_flag == True):
            f.write(VM_DEFAULT_CONFIG)

        self.node["nets"] = nets

    def has_option(self, config,section,option):
        if None != config.parser.option_dicts.get(option):
            if section in config.parser.option_dicts.get(option):
                return True
        return False

    def read_from_config(self):
        conf = cfgparse.ConfigParser()
        conf.add_file(VM_DEFAULT_CONFIG, type = 'ini')
        conf.parse()

        # initiation with values from configure options
        if self.has_option(conf, "main", "node") is True:
            node = conf.add_option("node", keys="main")
            self.node["name"] = node.get()
        if self.has_option(conf, "node", "mem_size") is True:
            mem_size = conf.add_option("mem_size", keys="node")
            self.node["mem_size"] = int(mem_size.get())
        if self.has_option(conf, "node", "vcpu_num") is True:
            vcpu_num = conf.add_option("vcpu_num", keys="node")
            self.node["vcpu_num"] = int(vcpu_num.get())
        if self.has_option(conf, "node", "vcpu_type") is True:
            vcpu_type = conf.add_option("vcpu_type", keys="node")
            self.node["vcpu_type"] = vcpu_type.get()
        if self.has_option(conf, "node", "pxeboot") is True:
            pxeboot = conf.add_option("pxeboot", keys="node")
            if pxeboot.get() == "yes":
                self.set_pxe()
        if self.has_option(conf, "node", "disk_num") is True:
            disk_num = conf.add_option("disk_num", keys="node")
            if self.has_option(conf, "node", "disk_size") is True:
                disk_size = conf.add_option("disk_size", keys="node")
                self.set_sata_disks_with_size(int(disk_num.get()),  int(disk_size.get()))
            else:
                self.set_sata_disks_with_size(int(disk_num.get()), 4)
        elif self.has_option(conf, "node", "disk_size") is True:
            disk_size = conf.add_option("disk_size", keys="node")
            self.set_sata_disks_with_size(1, int(disk_size.get()))
        if self.has_option(conf, "node", "network_mode") is True:
            nm = conf.add_option("network_mode", keys="node")
            bridge = ""
            if nm.get() == "bridge":
                bridge = conf.add_option("network_name", keys="node")
            self.set_network(nm, bridge.get())
        
        self.set_bios_data(self.node["name"])

    def render_vm_template(self):
        raw_xml = ""
        with open(VM_DEFAULT_XML, 'r') as f:
            raw_xml = f.read()
        template = jinja2.Template(raw_xml)
        self.render_xml = template.render(node=self.node)
        return self.render_xml

def start_vm(vm_desc):
    conn =libvirt.open()
    conn.createLinux(vm_desc, 0)
    conn.close()
    print check_qemu_version()


def stop_vm(node):
    conn = libvirt.open()
    domain = conn.lookupByName(node)

    domain.destroy()
    conn.close()


def status_vm(node):
    conn = libvirt.open()
    domainIDs = conn.listDomainsID()
    for id in domainIDs:
        domain = conn.lookupByID(id)
        if domain.name() == node:
            conn.close()
            return True
    return False


def check_vm_status(node):
    conn = libvirt.open()
    vm_exist_flag = False

    domainIDs = conn.listDomainsID()
    if len(domainIDs) == 1:
        domain = conn.lookupByID(domainIDs[0])
        if domain.name() == node:
            vm_exist_flag = True
        else:
           domain.destroy()
           vm_exist_flag = False
    elif len(domainIDs) > 1:
        for id in domainIDs:
            domain = conn.lookupByID(id)
            if domain.name() != node:
                domain.destroy()
            elif domain.name() == node:
                vm_exist_flag = True
            else:
                pass
    else:
        pass

    conn.close()
    return vm_exist_flag


def check_qemu_version():
    qemu_version_cmd = "/usr/bin/qemu-system-x86_64 -version"
    qemu_version_check = subprocess.Popen(qemu_version_cmd, shell=True,
                                          stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE)
    cmd_result = qemu_version_check.communicate()
    if qemu_version_check.returncode == 0:
        return "InfraSIM-QEMU 2.0 based on {}".format(
            cmd_result[0].split(",")[0])
    else:
        return cmd_result[1]
