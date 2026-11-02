"""Explain checked saved validation results without inference, EE calls or job writes."""
import re


ALIASES = {
    1: ('forest', 'forests'), 2: ('shrubland', 'shrublands', 'shrub land'),
    3: ('grassland', 'grasslands', 'grass land'),
    4: ('cultivated rainfed', 'rainfed', 'rain fed'),
    5: ('cultivated irrigated', 'irrigated'), 6: ('orchards', 'orchard'),
    7: ('bare soil/sand', 'bare soil', 'bare land', 'sand'), 8: ('rocks', 'rock'),
    9: ('built up', 'builtup', 'urban'), 10: ('artificial water',),
    11: ('seasonal water',), 12: ('sebkha', 'sabkha'),
}


def normalized(text):
    # Routing IDs must not be mistaken for years or class codes.
    text = re.sub(r'\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b', '', text, flags=re.I)
    return re.sub(r'\s+', ' ', text.lower().replace('’', "'").replace('-', ' ')).strip().rstrip('?.!')


def class_codes(text):
    text = normalized(text)
    codes = {code for code, aliases in ALIASES.items()
             if any(re.search(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', text) for alias in aliases)}
    codes.update(int(n) for n in re.findall(r'\bclass\s*#?\s*(\d+)\b', text))
    return sorted(codes)


def is_accuracy_question(text):
    text = normalized(text)
    if re.search(r'\b(?:accuracy|accuracies|kappa)\b|\bconfusion matrix\b|\bvalidation (?:results|metrics)\b', text):
        return True
    if re.search(r'\b(?:confused|confusion|misclassified|misclassification|classification errors)\b', text):
        return True
    if re.search(r'\bhow (?:accurate|well)\b', text) and re.search(r'\b(?:map|model|classifier|classification)\b', text):
        return True
    return bool(class_codes(text) and re.match(r'^(?:(?:and |what |how )?about |and |explain )', text))


def _pct(value):
    return 'not recorded' if value is None else f'{value:.2f}%'


def _class_description(report, code):
    row = report['classes'][code - 1]
    matrix = report['metrics']['confusion']
    i = code - 1
    correct, references = matrix[i][i], sum(matrix[i])
    predicted = sum(r[i] for r in matrix)
    lines = [f"{row['name']} (class {code}): recorded producer accuracy is {_pct(row['producer_percent'])}; "
             f"user accuracy is {_pct(row['user_percent'])}."]
    if references:
        lines.append(f"Of {references} reference samples of {row['name']}, {correct} were classified correctly "
                     f"and {references - correct} were assigned to other classes.")
    else:
        lines.append(f"There are no reference samples for {row['name']} in this saved validation matrix.")
    if predicted:
        lines.append(f"Of {predicted} samples predicted as {row['name']}, {correct} match the reference "
                     f"and {predicted - correct} belong to other reference classes.")
    else:
        lines.append(f"No validation samples were predicted as {row['name']}; user accuracy is unavailable.")
    errors = [(n, report['classes'][j]['name']) for j, n in enumerate(matrix[i]) if j != i and n]
    if errors:
        maximum = max(n for n, _ in errors)
        targets = ', '.join(name for n, name in errors if n == maximum)
        lines.append(f"The most frequent alternative prediction for reference {row['name']} was "
                     f"{targets}: {maximum} sample(s) per listed class.")
    elif references:
        lines.append('All reference samples of this class were classified correctly in this saved validation set.')
    return lines


def _confusions(report):
    matrix = report['metrics']['confusion']
    names = [r['name'] for r in report['classes']]
    pairs = sorted(((matrix[i][j] + matrix[j][i], i, j) for i in range(12) for j in range(i + 1, 12)
                    if matrix[i][j] + matrix[j][i]), key=lambda p: (-p[0], p[1], p[2]))
    if not pairs:
        return ['No off-diagonal errors are present in the saved validation matrix.'
                if report['metrics']['sampled_validation_count'] else 'There are no validation samples to compare.']
    cutoff = pairs[min(2, len(pairs) - 1)][0]
    lines = ['The largest class-pair confusions by validation sample count are listed below. '
             'Each total combines both directions; these are sample counts, not mapped areas.']
    for total, i, j in pairs:
        if total < cutoff:
            break
        lines.append(f"{names[i]} / {names[j]}: {total} errors in total. "
                     f"{matrix[i][j]} reference {names[i]} samples were predicted as {names[j]}; "
                     f"{matrix[j][i]} reference {names[j]} samples were predicted as {names[i]}.")
    return lines


def _summary(report):
    metrics = report['metrics']
    matrix = metrics['confusion']
    count = metrics['sampled_validation_count']
    correct = sum(matrix[i][i] for i in range(12))
    lines = [f"Recorded overall accuracy is {_pct(None if metrics['overall'] is None else metrics['overall'] * 100)}."]
    if count:
        lines.append(f"In the saved confusion matrix, {correct} of {count} validation samples were classified correctly; "
                     f"{count - correct} were assigned to a different class.")
    else:
        lines.append('The saved validation matrix contains no samples.')
    if metrics['kappa'] is not None:
        lines.append(f"Recorded Kappa is {metrics['kappa']:.4f}. It describes agreement adjusted for chance agreement; "
                     'it is not a percentage.')
    valid = [r for r in report['classes'] if r['producer_percent'] is not None and r['samples']]
    if valid:
        high, low = max(r['producer_percent'] for r in valid), min(r['producer_percent'] for r in valid)
        for label, value in [('Highest', high), ('Lowest', low)]:
            names = ', '.join(r['name'] for r in valid if r['producer_percent'] == value)
            lines.append(f'{label} recorded producer accuracy: {names} ({_pct(value)}). '
                         'This comparison concerns the reference samples for each class.')
    return lines


def explain_saved_accuracy(report, question):
    """Attach a focused answer, retaining every original value and source field."""
    if report.get('state') != 'available' or not question:
        return report
    text = normalized(question)
    codes = class_codes(text)
    metrics = report['metrics']
    years = re.findall(r'\b20\d{2}\b', text)
    unknown_class = bool(re.search(r'\b(?:accuracy|accuracies) (?:of|for) (?:the )?', text) and not codes and not years
                         and not re.search(r'\b(?:map|model|classification|tile|each class|all classes|tripoli)\b', text))
    title, paragraphs = None, []
    if years and any(int(y) != report['request']['target_year'] for y in years):
        title = 'Choose the saved map for that year'
        paragraphs = [f"The selected saved result is for {report['request']['target_year']}. "
                      'Select a saved map for the requested year to read its validation results. No new run was started.']
    elif any(code < 1 or code > 12 for code in codes) or unknown_class:
        title = 'Which land-cover class?'
        paragraphs = ['Use a class name from the legend or its code (1–12). '
                      'For example: Explain the accuracy of cultivated irrigated land.']
    elif codes:
        title = 'Class accuracy explained'
        for code in codes:
            paragraphs.extend(_class_description(report, code))
        if re.search(r'\bwhy\b|\bcause', text):
            paragraphs.append('The saved matrix records the errors, but does not identify their physical or data-related causes.')
    elif re.search(r'\b(?:confused|misclassified|misclassification|classification errors)\b', text):
        title, paragraphs = 'Which classes are confused?', _confusions(report)
        if re.search(r'\bwhy\b|\bcause', text):
            paragraphs.append('These counts do not establish why the errors occurred.')
    elif re.search(r"\bproducer'?s?\b", text) or re.search(r"\buser'?s?\b", text):
        title = 'Producer and user accuracy'
        paragraphs = [
            'Producer accuracy starts with the reference samples of a class: how many were classified correctly? '
            'Its denominator is the reference row total in the confusion matrix.',
            'User accuracy starts with the samples predicted as a class: how many match the reference? '
            'Its denominator is the prediction column total. Both measures describe validation samples, not class areas.',
            'Ask about a specific class, for example: Explain the accuracy of orchards.']
    elif 'kappa' in text:
        title = 'Kappa explained'
        paragraphs = [('Recorded Kappa is not available.' if metrics['kappa'] is None else f"Recorded Kappa is {metrics['kappa']:.4f}.") +
                      ' Kappa compares observed agreement with the agreement expected from the reference and predicted class totals. '
                      'A value of 1 means perfect agreement in the evaluated samples, 0 means agreement at that chance baseline, '
                      'and negative values mean lower agreement. It is not a percentage or an overall accuracy score.']
    elif re.search(r'\b(?:interpret|explain|summarize|summarise|summary|meaning|mean|good|reliable)\b|\bhow (?:accurate|well)\b', text):
        title, paragraphs = 'Accuracy explained', _summary(report)
        if re.search(r'\b(?:good|reliable)\b', text):
            paragraphs.append('These saved results alone do not establish suitability for every use; '
                              'that depends on the decisions and classes you need the map for.')
    if title is None:
        return report
    return {**report, 'explanation': {'title': title, 'paragraphs': paragraphs, 'class_codes': codes}}
