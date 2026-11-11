# SMS Gora for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![tests](https://github.com/TekservixHQ/ha-smsgora/actions/workflows/tests.yml/badge.svg)](https://github.com/TekservixHQ/ha-smsgora/actions/workflows/tests.yml)

Send SMS alerts from Home Assistant through your own Android phones with [SMS Gora](https://tekservix.com/smsgora/), and trigger automations when an SMS arrives.

SMS alerts still reach people when there is no internet or app: alarms, water leaks, power cuts, a door left open. SMS Gora sends them from an ordinary SIM card in an Android phone you link to your account, so there's no sender ID registration and no per-message fee from us; your mobile operator bills the texts like any SMS.

## What you get

- **Notify entity**: use `notify.send_message` in any automation to text your default recipients
- **`smsgora.send_sms` action**: text any numbers, choose the phone and SIM
- **Incoming SMS events**: `smsgora_sms_received` (with `from` and `message`) to build SMS commands like "STATUS" or "ARM"
- **Delivery events**: `smsgora_sms_status` for sent, delivered and failed reports
- Every incoming webhook is checked against its HMAC-SHA256 signature

## Requirements

- A Tekservix account with SMS Gora and an API key (SMS Gora → API keys)
- An Android phone with a SIM card linked in the SMS Gora app
- For incoming SMS events: Home Assistant reachable from the internet (Home Assistant Cloud, or your own domain set as the external URL). Sending works without it.

## Install

1. In HACS, open the menu → **Custom repositories**, add `https://github.com/TekservixHQ/ha-smsgora` with type **Integration**.
2. Install **SMS Gora** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → SMS Gora**, paste your API key and, optionally, default recipients (comma separated) and a phone ID.

When Home Assistant has an external URL, the integration registers its webhook in SMS Gora automatically, and removes it again when you delete the integration.

## Examples

Text the household when the alarm triggers:

```yaml
automation:
  - alias: "SMS on alarm"
    triggers:
      - trigger: state
        entity_id: alarm_control_panel.home
        to: triggered
    actions:
      - action: notify.send_message
        target:
          entity_id: notify.sms_gora
        data:
          title: "ALARM"
          message: "The alarm was triggered at {{ now().strftime('%H:%M') }}"
```

Text a specific number from the second SIM:

```yaml
- action: smsgora.send_sms
  data:
    to: "+15551234567, +447700900123"
    message: "Water leak detected in the basement"
    sim_slot: 1
```

Reply to an SMS command:

```yaml
automation:
  - alias: "SMS STATUS command"
    triggers:
      - trigger: event
        event_type: smsgora_sms_received
    conditions:
      - condition: template
        value_template: "{{ trigger.event.data.message | trim | upper == 'STATUS' }}"
    actions:
      - action: smsgora.send_sms
        data:
          to: "{{ trigger.event.data.from }}"
          message: "Alarm: {{ states('alarm_control_panel.home') }}, inside {{ states('sensor.living_room_temperature') }}°C"
```

Only act on SMS from numbers you trust: check `trigger.event.data.from` in the condition.

## More from Tekservix

- [WAservix for Home Assistant](https://github.com/TekservixHQ/ha-waservix): the same for WhatsApp, from your own number
- [AI Sales Agent](https://tekservix.com/ai-sales-agent) and [Website to App](https://tekservix.com/mobile-apps)
- SMS Gora libraries for many languages: [github.com/TekservixHQ](https://github.com/TekservixHQ)

## License

MIT
