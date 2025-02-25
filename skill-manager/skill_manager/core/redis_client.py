from skill_manager.settings.redis_settings import RedisSettings
from redis import Redis

class RedisClient():
    def connect(self):
        self.redis_settings = RedisSettings()
        self.client = Redis(
            host=self.redis_settings.host,
            port=self.redis_settings.port,
            password=self.redis_settings.password,
            username=self.redis_settings.username,
        )
    def close(self):
        self.client.close()
