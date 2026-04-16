from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "dora"
    postgres_host: str = "db"
    postgres_port: int = 5432

    github_token: str = ""
    github_orgs: str = ""   # comma-separated org/user names e.g. "myorg,anotherorg"
    github_repos: str = ""  # comma-separated explicit repos e.g. "owner/repo1,owner/repo2"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
