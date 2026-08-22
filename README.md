# Text to VCF

Alfred workflow that pulls contacts out of a block of text and hands them to
Contacts.

Copy an email signature, a business card you typed out, a message with names
and numbers in it. Type `vcf`. The text goes to OpenAI, comes back as
structured contacts, and Contacts opens with them ready to add.

![icon](icon.png)

## Requirements

* Alfred 5 with the Powerpack
* Python 3 (the one from the Command Line Tools works)
* An OpenAI API key

Standard library only. Nothing to install.

## Setup

**Get an API key** from [platform.openai.com](https://platform.openai.com/api-keys).
The workflow bills against your own account. A signature costs a fraction of a
cent with the default model.

**Install the workflow.** Download `Alfred-Text-to-VCF.alfredworkflow` from
[releases](https://github.com/hendryque/alfred-text-to-vcf/releases) and
double-click it.

**Add the key.** Open Alfred, Workflows, Text to VCF, Configure workflow. Or
leave the field empty and put the key in `~/.config/openai-key` instead.

The key is marked non-exporting, so it stays behind if you share the workflow.

## Usage

```
vcf
```

with text on the clipboard, or

```
vcf Dr Erika Mustermann, Beispiel GmbH, +43 664 1234567
```

Phone and email types are recognised where the text gives them away, so a
number labelled mobile lands as `TEL;TYPE=CELL` rather than a bare number.

The original text is kept in the note field, so you can see later what the
contact was built from.

## Configuration

| Setting | Default | Notes |
|---|---|---|
| `OPENAI_API_KEY` | reads `~/.config/openai-key` | |
| `TEXT_TO_VCF_MODEL` | `gpt-4.1` | Any chat model that supports structured output |

## Command line

`src/text_to_vcf.py` runs on its own:

```sh
OPENAI_API_KEY=sk-... ./src/text_to_vcf.py "Erika Mustermann, Beispiel GmbH"
pbpaste | OPENAI_API_KEY=sk-... ./src/text_to_vcf.py
```

## What gets sent

The text you pass goes to OpenAI's API. Nothing else leaves your machine, and
nothing is stored by this workflow. Contact details are personal data, often
someone else's, so think about whose information you are sending before you
run it. Check OpenAI's data policy for what happens on their side.

## Troubleshooting

**No API key.** Neither the workflow field nor `~/.config/openai-key` had one.

**OpenAI rejected the key (401).** Wrong or revoked key.

**Rate limited or out of quota (429).** Your account has no credit, or you hit
a limit.

**No contacts found in text.** The model saw nothing that looked like a person.

## Licence

MIT, see [LICENSE](LICENSE).

The icon comes from Apple's SF Symbols. Apple allows SF Symbols in software
running on Apple platforms and restricts redistribution of the artwork by
itself. As a workflow icon that is covered. Replace it if you port this
elsewhere.
