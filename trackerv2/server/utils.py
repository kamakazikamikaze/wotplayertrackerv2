from uuid import NAMESPACE_DNS, uuid5


def genuuid(ip):
    return str(uuid5(NAMESPACE_DNS, ip))
