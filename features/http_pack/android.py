"""Android projection of existing HTTP edit options."""


def editFields(task) -> dict:
    step = task.steps[0]
    return {
        "url": task.url,
        "headers": dict(step.headers),
        "clientProfile": step.clientProfile,
        "userAgent": step.userAgent,
        "subworkerCount": step.subworkerCount,
    }
