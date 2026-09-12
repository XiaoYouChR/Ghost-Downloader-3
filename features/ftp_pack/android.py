def editFields(task) -> dict:
    return {"subworkerCount": task.steps[0].subworkerCount}
