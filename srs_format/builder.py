class TemplateBuilder(dict):
    def __init__(self, name, front, **kwargs):
        super(TemplateBuilder, self).__init__(
            name=name,
            front=front,
            **kwargs
        )
