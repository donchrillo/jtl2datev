from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_OWN_VAT_COUNTRIES: frozenset[str] = frozenset({"DE", "FR", "IT", "ES", "PL", "CZ", "GB"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    sql_server: str = "localhost"
    sql_port: int = 50000
    sql_database: str = "eazybusiness"
    sql_username: str = "sa"
    sql_password: SecretStr = SecretStr("")

    datev_mandantennr: int | None = None
    datev_beraternr: int | None = None

    own_vat_countries: frozenset[str] = _DEFAULT_OWN_VAT_COUNTRIES

    @field_validator("own_vat_countries", mode="before")
    @classmethod
    def parse_own_vat_countries(cls, v: object) -> frozenset[str]:
        if isinstance(v, str):
            return frozenset(c.strip().upper() for c in v.split(",") if c.strip())
        if isinstance(v, (list, tuple, set, frozenset)):
            return frozenset(str(c).strip().upper() for c in v)
        return _DEFAULT_OWN_VAT_COUNTRIES

    @property
    def sqlalchemy_url(self) -> str:
        pw = self.sql_password.get_secret_value()
        return (
            f"mssql+pyodbc://{self.sql_username}:{pw}"
            f"@{self.sql_server}:{self.sql_port}/{self.sql_database}"
            "?driver=ODBC+Driver+18+for+SQL+Server"
            "&TrustServerCertificate=yes"
            "&Encrypt=yes"
        )
