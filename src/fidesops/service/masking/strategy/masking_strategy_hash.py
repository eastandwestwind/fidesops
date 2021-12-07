import hashlib
import secrets
from typing import Optional, List

from fidesops.core.config import config
from fidesops.schemas.masking.masking_configuration import (
    HashMaskingConfiguration,
    MaskingConfiguration,
)
from fidesops.schemas.masking.masking_secrets import MaskingSecret, SecretType
from fidesops.schemas.masking.masking_strategy_description import (
    MaskingStrategyDescription,
    MaskingStrategyConfigurationDescription,
)
from fidesops.service.masking.strategy.format_preservation import FormatPreservation
from fidesops.service.masking.strategy.masking_strategy import MaskingStrategy


HASH = "hash"


class HashMaskingStrategy(MaskingStrategy):
    """Masks a value by hashing it"""

    def __init__(
        self,
        configuration: HashMaskingConfiguration,
    ):
        self.algorithm = configuration.algorithm
        if self.algorithm == HashMaskingConfiguration.Algorithm.SHA_256:
            self.algorithm_function = self._hash_sha256
        elif self.algorithm == HashMaskingConfiguration.Algorithm.SHA_512:
            self.algorithm_function = self._hash_sha512
        self.format_preservation = configuration.format_preservation

    def mask(self, value: Optional[str]) -> Optional[str]:
        """Returns the hashed version of the provided value. Returns None if the provided value
        is None"""
        if value is None:
            return None
        masked: str = self.algorithm_function(value, self.salt)
        if self.format_preservation is not None:
            formatter = FormatPreservation(self.format_preservation)
            return formatter.format(masked)
        return masked

    def generate_secrets(self) -> List[MaskingSecret]:
        secret_types = {SecretType.salt}
        masking_secrets = []
        for secret_type in secret_types:
            secret = secrets.token_urlsafe(config.security.DEFAULT_ENCRYPTION_BYTE_LENGTH)
            masking_secrets.append(MaskingSecret(secret=secret, masking_strategy=HASH, secret_type=secret_type))
        return masking_secrets

    @staticmethod
    def get_configuration_model() -> MaskingConfiguration:
        return HashMaskingConfiguration

    # MR Note - We will need a way to ensure that this does not fall out of date. Given that it
    # includes subjective instructions, this is not straightforward to automate
    @staticmethod
    def get_description() -> MaskingStrategyDescription:
        return MaskingStrategyDescription(
            name=HASH,
            description="Masks the input value by returning a hashed version of the input value",
            configurations=[
                MaskingStrategyConfigurationDescription(
                    key="algorithm",
                    description="Specifies the hashing algorithm to be used. Can be SHA-256 or "
                    "SHA-512. If not provided, default is SHA-256",
                ),
                MaskingStrategyConfigurationDescription(
                    key="format_preservation",
                    description="Option to preserve format in masking, with a provided suffix",
                )
            ],
        )

    @staticmethod
    def data_type_supported(data_type: Optional[str]) -> bool:
        """Determines whether or not the given data type is supported by this masking strategy"""
        supported_data_types = {"string"}
        return data_type in supported_data_types

    # Helpers

    @staticmethod
    def _hash_sha256(value: str, salt: str) -> str:
        return hashlib.sha256(
            (value + salt).encode(config.security.ENCODING)
        ).hexdigest()

    @staticmethod
    def _hash_sha512(value: str, salt: str) -> str:
        return hashlib.sha512(
            (value + salt).encode(config.security.ENCODING)
        ).hexdigest()
