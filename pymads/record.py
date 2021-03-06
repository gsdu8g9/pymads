'''
This file is part of Pymads.

Pymads is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Pymads is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with Pymads.  If not, see <http://www.gnu.org/licenses/>
'''

import struct
import logging
from collections import namedtuple
from socket import inet_pton, inet_ntop, AF_INET, AF_INET6
from persei import String, RawData, RawDataDecorator
from pymads import const
from pymads import utils

soa_namedtuple = namedtuple(
    'SOAType',
    ['mname', 'rname', 'serial', 'refresh', 'retry', 'expire', 'minimum']
)

class SOAType(soa_namedtuple):
    def __str__(self):
        return "%s.\t%s.\t%d\t%d\t%d\t%d\t%d" % self

class Record(object):
    ''' Represents a DNS record. '''

    def __init__(self, domain_name, rdata, 
                    rtype="A", rttl=1800, rclass="IN"):
        '''
            domain_name : A straightforward FQDN or PQDN
            rdata       : For most records, just IP string.
            rtype       : Record type. Usually A or AAAA.
            rttl        : Time-to-live (expiration data).
            rclass      : Almost always IN for Internet.
        '''
        self.domain_name = domain_name
        self.rtype  = rtype
        self.rttl   = int(rttl)
        self.rclass = rclass
        # Set last because implicit packing depends on type and class
        self.rdata  = rdata

    @property
    def rdata(self):
        '''
        Field that contains the "contents" of the record.
        '''
        return self._rdata

    @rdata.setter
    def rdata(self, value):
        '''
        Setter for rdata that also sets up self.rdata_packed eagerly.
        '''
        self._rdata = value
        self.rdata_packed = self.pack_rdata()

    @property
    def rtype(self):
        '''
        Record type. Usually A or AAAA.
        '''
        return self._rtype

    @rtype.setter
    def rtype(self, value):
        '''
        Setter for record type. Accepts either textual or int code.
        '''
        self._rtype = const.get_label(const.RECORD_TYPES, value)

    @property
    def rclass(self):
        '''
        Record class. Almost always IN.
        '''
        return self._rclass

    @rclass.setter
    def rclass(self, value):
        '''
        Setter for record class. Accepts either textual or int code.
        '''
        self._rclass = const.get_label(const.RECORD_CLASSES, value)

    @property
    def rtypecode(self):
        '''
        Numeric code for this record's type.
        '''
        return const.RECORD_TYPES[self._rtype]

    @property
    def rclasscode(self):
        '''
        Numeric code for this record's class.
        '''
        return const.RECORD_CLASSES[self._rclass]

    def __eq__(self, other):
        return (isinstance(other, Record) and hash(self) == hash(other))

    def __hash__(self):
        return hash((
            self.domain_name,
            self.rdata,
            self.rtype,
            self.rttl,
            self.rclass,
        ))

    def __repr__(self):
        return "<record for %s: %d %s %s %s>" % (
            self.domain_name,
            self.rttl,
            self.rtype,
            self.rclass,
            self.rdata,
        )

    def __str__(self):
        text = '%s.\t%d\t%s\t%s\t%s' % (
           self.domain_name,
           self.rttl,
           self.rclass,
           self.rtype,
           self.rdata
        )

        if self.packtype == 'domain':
           text += '.'

        return text

    @property
    def packtype(self):
        if self.rtype in ('A',):
            return 'IPv4'
        elif self.rtype in ('AAAA',):
            return 'IPv6'
        elif self.rtype in ('NS', 'CNAME'):
            return 'domain'
        elif self.rtype in ('SOA',):
            return 'zone'
        else:
            logging.warn('unknown record type ' + self.rtype)
            return 'unknown'

    @RawDataDecorator()
    def pack_rdata(self):
        '''
        Create the binary representation of the rdata for use in responses.

        Returns as RawData.
        '''
        funcname = 'pack_rdata_' + self.packtype
        if hasattr(self, funcname):
            return getattr(self, funcname)()
        else:
            return self.rdata

    def pack_rdata_IPv4(self):
        '''
        Pack an IPv4 record.
        '''
        return inet_pton(AF_INET, self.rdata)

    def pack_rdata_IPv6(self):
        '''
        Pack an IPv6 record.
        '''
        return inet_pton(AF_INET6, self.rdata)

    def pack_rdata_domain(self):
        '''
        Pack a record that holds an encoded domain name.
        '''
        return utils.labels2str(self.rdata.split('.'))

    def pack_rdata_zone(self):
        '''
        Pack a record that holds global parameters of a zone.
        '''
        if type(self.rdata) is dict:
            if set(self.rdata.keys()) != set(SOAType._fields):
                raise TypeError("invalid SOA record")
            self.rdata = SOAType(*[self.rdata[f] for f in SOAType._fields])
        elif type(self.rdata) in (tuple, list):
            self.rdata = SOAType(*self.rdata)

        packed  = utils.labels2str(self.rdata.mname.split('.'))
        packed += utils.labels2str(self.rdata.rname.split('.'))
        packed += struct.pack("!IiiiI", *self.rdata[2:])
        return packed

    @RawDataDecorator(args=False)
    def unpack_rdata(self, data, offset, length):
        '''
        Decode binary rdata.

        Returns as RawData.
        '''
        subset = RawData(data[offset:offset+length])

        funcname_subset = 'unpack_rdata_subset_' + self.packtype
        funcname_offset = 'unpack_rdata_offset_' + self.packtype

        if hasattr(self, funcname_subset):
            return getattr(self, funcname_subset)(subset)
        elif hasattr(self, funcname_offset):
            return getattr(self, funcname_offset)(data, offset, length)
        else:
            return subset

    def unpack_rdata_subset_IPv4(self, subset):
        '''
        Unpack an IPv4 record.
        '''
        return inet_ntop(AF_INET, subset.export())

    def unpack_rdata_subset_IPv6(self, subset):
        '''
        Unpack an IPv6 record.
        '''
        return inet_ntop(AF_INET6, subset.export())

    def unpack_rdata_offset_domain(self, data, offset, length):
        '''
        Unpack a record that holds an encoded domain name.
        '''
        return '.'.join(
            String(x).export()
            for x in utils.str2labels(data, offset)[1]
        )

    def unpack_rdata_offset_zone(self, data, offset, length):
        '''
        Unpack a record that holds global parameters of a zone.
        '''
        offset, mname = utils.str2labels(data, offset)
        offset, rname = utils.str2labels(data, offset)

        return SOAType(
            '.'.join(String(x).export() for x in mname),
            '.'.join(String(x).export() for x in rname),
            *struct.unpack("!IiiiI", data[offset:offset+20].export())
        )

    def pack(self):
        '''
        Formats the resource fields to be used in the response packet.
        '''

        packed  = utils.labels2str(
            RawData(x) for x in self.domain_name.split('.')
        )
        packed += struct.pack(
            "!HHIH",
             self.rtypecode,
             self.rclasscode,
             self.rttl,
             len(self.rdata_packed)
        )
        return RawData(packed) + self.rdata_packed

    def unpack(self, source, offset=0):
        '''
        Decodes data into instance properties
        '''
        offset, labels = utils.str2labels(source, offset)
        self.domain_name = '.'.join(String(x).export() for x in labels)

        (
            self.rtype,
            self.rclass,
            self.rttl,
            rdata_len
        ) = struct.unpack("!HHIH", source[offset:offset+10].export())
        offset += 10
        self.rdata = self.unpack_rdata(source, offset, rdata_len)
        return offset + rdata_len
