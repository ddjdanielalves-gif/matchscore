def _pick(self, method: str, *args, **kwargs):
    try:
        # Tenta chamar com args posicionais E kwargs
        if args and kwargs:
            value = getattr(self.primary, method)(*args, **kwargs)
        elif args:
            value = getattr(self.primary, method)(*args)
        elif kwargs:
            value = getattr(self.primary, method)(**kwargs)
        else:
            value = getattr(self.primary, method)()
            
        if value is None:
            raise RuntimeError(f"{method} returned None")
        self.sources_used.add(self.primary.source)
        return value
    except Exception as exc:
        logger.warning("Falling back to demo for %s: %s", method, exc)
        # Mesma lógica para o fallback
        if args and kwargs:
            value = getattr(self.fallback, method)(*args, **kwargs)
        elif args:
            value = getattr(self.fallback, method)(*args)
        elif kwargs:
            value = getattr(self.fallback, method)(**kwargs)
        else:
            value = getattr(self.fallback, method)()
        self.sources_used.add(self.fallback.source)
        return value
