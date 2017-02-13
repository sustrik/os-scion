# Copyright 2014 ETH Zurich
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
:mod:`trc` --- SCION TRC parser
===============================================
"""
# Stdlib
import base64
import copy
import json
import logging
import time

# External
import lz4

# SCION
from lib.crypto.asymcrypto import verify, sign
from lib.packet.scion_addr import ISD_AS

ISDID_STRING = 'ISDID'
DESCRIPTION_STRING = 'Description'
VERSION_STRING = 'Version'
CREATION_TIME_STRING = 'CreationTime'
CORE_ASES_STRING = 'CoreCAs'
ROOT_CAS_STRING = 'RootCAs'
PKI_LOGS_STRING = 'PKILogs'
QUORUM_EEPKI_STRING = 'QuorumEEPKI'
ROOT_RAINS_KEY_STRING = 'RootRainsKey'
QUORUM_OWN_TRC_STRING = 'QuorumOwnTRC'
QUORUM_CAS_STRING = 'QuorumCAs'
QUARANTINE_STRING = 'Quarantine'
SIGNATURES_STRING = 'Signatures'
GRACE_PERIOD_STRING = 'GracePeriod'
ONLINE_KEY_ALG_STRING = 'OnlineKeyAlg'
ONLINE_KEY_STRING = 'OnlineKey'
OFFLINE_KEY_ALG_STRING = 'OfflineKeyAlg'
OFFLINE_KEY_STRING = 'OfflineKey'


class TRC(object):
    """
    The TRC class parses the TRC file of an ISD and stores such
    information for further use.

    :ivar int isd: the ISD identifier.
    :ivar str description: is a human readable description of an ISD.
    :ivar int version: the TRC file version.
    :ivar int creation_time: the TRC file creation timestamp.
    :ivar dict core_ases: the set of core ASes and their certificates.
    :ivar dict root_cas: the set of root CAs and their certificates.
    :ivar dict pki_logs: is a dictionary of end entity certificate logs, and
        their addresses and public key certificates
    :ivar int quroum_eepki: is a threshold number (nonnegative integer) of
        CAs that have to sign a domain’s policy
    :ivar str root_rains_key: the RAINS root public key.
    :ivar int quorum_own_trc: number of core ASes necessary to sign a new TRC.
    :ivar int quorum_cas: number of CAs necessary to change CA entries
    :ivar int grace_period: defines for how long this TRC is valid when a new
        TRC is available
    :ivar bool quarantine: flag defining whether TRC is valid(quarantine=false)
        or an early annoncement(quarantine=true)
    :ivar dict signatures: signatures generated by a quorum of trust roots.
    """

    FIELDS_MAP = {
        ISDID_STRING: ("isd", int),
        DESCRIPTION_STRING: ("description", str),
        VERSION_STRING: ("version", int),
        CREATION_TIME_STRING: ("time", int),
        CORE_ASES_STRING: ("core_ases", dict),
        ROOT_CAS_STRING: ("root_cas", dict),
        PKI_LOGS_STRING: ("pki_logs", dict),
        QUORUM_EEPKI_STRING: ("quorum_eepki", int),
        ROOT_RAINS_KEY_STRING: ("root_rains_key", bytes),
        QUORUM_OWN_TRC_STRING: ("quorum_own_trc", int),
        QUORUM_CAS_STRING: ("quorum_cas", int),
        QUARANTINE_STRING: ("quarantine", bool),
        SIGNATURES_STRING: ("signatures", dict),
        GRACE_PERIOD_STRING: ("grace_period", int),
    }

    def __init__(self, trc_dict):
        """
        :param dict trc_dict: TRC as dict.
        """
        for k, (name, type_) in self.FIELDS_MAP.items():
            val = trc_dict[k]
            if type_ in (int,):
                val = int(val)
            elif type_ in (dict, ):
                val = copy.deepcopy(val)
            setattr(self, name, val)
        for subject in trc_dict[CORE_ASES_STRING]:
            key_ = trc_dict[CORE_ASES_STRING][subject][ONLINE_KEY_STRING]
            self.core_ases[subject][ONLINE_KEY_STRING] = \
                base64.b64decode(key_.encode('utf-8'))
        for subject in trc_dict[SIGNATURES_STRING]:
            self.signatures[subject] = \
                base64.b64decode(trc_dict[SIGNATURES_STRING][subject])

    def get_isd_ver(self):
        return self.isd, self.version

    def get_core_ases(self):
        res = []
        for key in self.core_ases:
            res.append(ISD_AS(key))
        return res

    def dict(self, with_signatures):
        """
        Return the TRC information.

        :param bool with_signatures:
            If True, include signatures in the return value.
        :returns: the TRC information.
        :rtype: dict
        """
        trc_dict = {}
        for k, (name, _) in self.FIELDS_MAP.items():
            trc_dict[k] = getattr(self, name)
        if not with_signatures:
            del trc_dict[SIGNATURES_STRING]
        return trc_dict

    @classmethod
    def from_raw(cls, trc_raw, lz4_=False):
        if lz4_:
            trc_raw = lz4.loads(trc_raw).decode("utf-8")
        trc = json.loads(trc_raw)
        return TRC(trc)

    @classmethod
    def from_values(cls, isd, description, version, core_ases, root_cas,
                    pki_logs, quorum_eepki, root_rains_key, quorum_own_trc,
                    quorum_cas, grace_period, quarantine, signatures):
        """
        Generate a TRC instance.
        """
        now = int(time.time())
        trc_dict = {
            ISDID_STRING: isd,
            DESCRIPTION_STRING: description,
            VERSION_STRING: version,
            CREATION_TIME_STRING: now,
            CORE_ASES_STRING: core_ases,
            ROOT_CAS_STRING: root_cas,
            PKI_LOGS_STRING: pki_logs,
            QUORUM_EEPKI_STRING: quorum_eepki,
            ROOT_RAINS_KEY_STRING: root_rains_key,
            QUORUM_OWN_TRC_STRING: quorum_own_trc,
            QUORUM_CAS_STRING: quorum_cas,
            GRACE_PERIOD_STRING: grace_period,
            QUARANTINE_STRING: quarantine,
            SIGNATURES_STRING: signatures,
        }
        trc = TRC(trc_dict)
        return trc

    def sign(self, isd_as, sig_priv_key):
        data = self._sig_input()
        self.signatures[isd_as] = base64.b64encode(sign(data, sig_priv_key)). \
            decode('utf-8')

    def verify(self, old_trc):
        """
        Perform signature verification for core signatures as defined
        in old TRC.

        :param: old_trc: the previous TRC which has already been verified.
        :returns: True if verification succeeds, false otherwise.
        :rtype: bool
        """
        # Only look at signatures which are from core ASes as defined in old TRC
        signatures = {k: self.signatures[k] for k in old_trc.core_ases.keys()}
        # We have more signatures than the number of core ASes in old TRC
        if len(signatures) < len(self.signatures):
            logging.warning("TRC has more signatures than number of core ASes.")
        valid_signature_signers = set()
        # Add every signer to this set whose signature was verified successfully
        for signer in signatures:
            public_key = self.core_ases[signer].subject_sig_key_raw
            if self._verify_signature(signatures[signer], public_key):
                valid_signature_signers.add(signer)
            else:
                logging.warning("TRC contains a signature which could not \
                be verified.")
        # We have fewer valid signatrues for this TRC than quorum_own_trc
        if len(valid_signature_signers) < old_trc.quorum_own_trc:
            logging.error("TRC does not have the number of required valid \
            signatures")
            return False
        logging.debug("TRC verified.")
        return True

    def _verify_signature(self, signature, public_key):
        """
        Checks if the signature can be verified with the given public key for a
        single signature

        :returns: True if the given signature could be verified with the
            given key, False otherwise
        :rtype bool
        """
        if not verify(self._sig_input(), signature, public_key):
            return False
        return True

    def _sig_input(self):
        d = self.dict(False)
        for k in d:
            if self.FIELDS_MAP[k][1] == str:
                d[k] = base64.b64encode(d[k].encode('utf-8')).decode('utf-8')
            elif self.FIELDS_MAP[k][1] == dict:
                d[k] = self._encode_dict(d[k])
        j = json.dumps(d, sort_keys=True, separators=(',', ':'))
        return j.encode('utf-8')

    def _encode_dict(self, dict_):
        encoded_dict = {}
        for key_ in dict_:
            if type(dict_[key_]) is str:
                encoded_dict[key_] = base64.b64encode(
                    dict_[key_].encode('utf-8')).decode('utf-8')
        return encoded_dict

    def to_json(self, with_signatures=True):
        """
        Convert the instance to json format.
        """
        trc_dict = copy.deepcopy(self.dict(with_signatures))
        core_ases = {}
        for subject in trc_dict[CORE_ASES_STRING]:
            d = trc_dict[CORE_ASES_STRING][subject]
            for key_ in (ONLINE_KEY_STRING, OFFLINE_KEY_STRING, ):
                key_str = trc_dict[CORE_ASES_STRING][subject][key_]
                base64.b64encode(key_str.encode('utf-8')).decode('utf-8')
            core_ases[subject] = d
        trc_dict[CORE_ASES_STRING] = core_ases
        if with_signatures:
            signatures = {}
            for subject in trc_dict[SIGNATURES_STRING]:
                signature = trc_dict[SIGNATURES_STRING][subject]
                signatures[subject] = base64.b64encode(
                    signature.encode('utf-8')).decode('utf-8')
            trc_dict[SIGNATURES_STRING] = signatures
        trc_str = json.dumps(trc_dict, sort_keys=True, indent=4)
        return trc_str

    def pack(self, lz4_=False):
        ret = self.to_json().encode('utf-8')
        if lz4_:
            return lz4.dumps(ret)
        return ret

    def __str__(self):
        return self.to_json()

    def __eq__(self, other):  # pragma: no cover
        return str(self) == str(other)


def verify_new_trc(old_trc, new_trc):
    """
    Check if update from current TRC to updated TRC is valid. Checks if update
    is correct and checks if the new TRC has enough valid signatures as defined
    in the current TRC.

    :returns: True if update is valid, False otherwise
    """
    # Check if update is correct
    if old_trc.isd != new_trc.isd:
        logging.error("TRC isdid mismatch")
        return False
    if old_trc.version + 1 != new_trc.version:
        logging.error("TRC versions mismatch")
        return False
    if new_trc.time < old_trc.time:
        logging.error("New TRC timestamp is not valid")
        return False
    if new_trc.quarantine or old_trc.quarantine:
        logging.error("Early announcement")
        return False
    # Check if there are enough valid signatures for new TRC
    if not new_trc.verify(old_trc):
        logging.error("New TRC verification failed, missing or \
        invalid signatures")
        return False
    logging.debug("New TRC verified")
    return True
