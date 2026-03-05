class Action:
    key: str = ""
    label: str = ""
    aliases: tuple = ()

    def matches(self, key: str) -> bool:
        return key == self.key or key in self.aliases

    def enabled(self, s, row) -> bool:
        return True

    def run(self, *args, **kwargs):
        raise NotImplementedError
