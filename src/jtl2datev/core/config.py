from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    sql_server: str = "localhost"
    sql_port: int = 50000
    sql_database: str = "eazybusiness"
    sql_username: str = "sa"
    sql_password: SecretStr = SecretStr("")

    datev_mandantennr: int | None = None
    datev_beraternr: int | None = None

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
