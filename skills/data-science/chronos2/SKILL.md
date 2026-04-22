---
name: chronos2
description: >
  Forecast numerical time series with Amazon Chronos-2 from Hugging Face.
  Use this skill whenever the user asks to forecast values over time, predict
  trends, project future numeric data, extrapolate a metric, or estimate future
  points from historical observations. This skill expects historical numeric
  values ordered oldest first, a forecast horizon, and a frequency code
  (`D`, `H`, `W`, or `M`), then runs Chronos2Pipeline in Python via
  execute_code or terminal and returns low/median/high forecast lines from the
  10th, 50th, and 90th percentiles.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [time-series, forecasting, chronos-2, huggingface, pytorch, data-science]
    category: data-science
---

# Chronos-2 Time Series Forecasting

Use Amazon Chronos-2 for zero-shot or light-touch time series forecasting when
the user provides numeric history and wants projected future values.

## Trigger Conditions

Use this skill when the user asks to:

- Forecast a time series
- Predict future values or future trend direction
- Project a numeric metric over time
- Extrapolate daily, hourly, weekly, or monthly observations

Typical examples:

- "Forecast next 14 days of sales from this history"
- "Predict the next 24 hourly readings"
- "Project weekly signups for the next 8 weeks"

## Required Inputs

Collect or confirm these inputs before running a forecast:

- `historical_data`: list of numeric values, ordered oldest first
- `steps`: integer number of future periods to forecast
- `frequency`: one of `D`, `H`, `W`, `M`

If the user provides fewer than 10 historical points, warn that the forecast
may be unstable because the context is short.

## Environment Setup

Install the required packages before the first run:

```bash
pip install "chronos-forecasting>=2.0" torch
```

Important note:

- The first model load downloads `amazon/chronos-2`, which is roughly 500 MB.
- Default to CPU.
- If CUDA is available, you may switch to CUDA for faster inference.

## Execution Rule

Use `execute_code` or terminal to run Python for the forecast. Prefer a single
Python script that:

1. Validates the inputs
2. Detects whether CUDA is available
3. Loads `Chronos2Pipeline`
4. Runs prediction with quantile levels `[0.1, 0.5, 0.9]`
5. Prints exactly three forecast lines: low, median, high

## Standard Python Pattern

Start from this pattern:

```python
from chronos import Chronos2Pipeline
import torch

pipeline = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map="cpu")
context = torch.tensor(historical_data, dtype=torch.float32).unsqueeze(0)
forecast = pipeline.predict(context, prediction_length=steps, quantile_levels=[0.1, 0.5, 0.9])
```

For production use in the skill flow, adapt it to support CPU by default and
CUDA when available:

```python
from chronos import Chronos2Pipeline
import torch

historical_data = [120.0, 123.0, 119.0, 126.0, 128.0, 131.0, 130.0, 133.0, 137.0, 139.0]
steps = 5
frequency = "D"

if len(historical_data) < 10:
    print("Warning: fewer than 10 historical data points were provided; forecast quality may be unstable.")

if frequency not in {"D", "H", "W", "M"}:
    raise ValueError("frequency must be one of: D, H, W, M")

device = "cuda" if torch.cuda.is_available() else "cpu"
pipeline = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map=device)

context = torch.tensor(historical_data, dtype=torch.float32).unsqueeze(0)
if device == "cuda":
    context = context.to("cuda")

forecast = pipeline.predict(
    context,
    prediction_length=steps,
    quantile_levels=[0.1, 0.5, 0.9],
)

low = forecast[0, :, 0].detach().cpu().tolist()
median = forecast[0, :, 1].detach().cpu().tolist()
high = forecast[0, :, 2].detach().cpu().tolist()

print("low:", low)
print("median:", median)
print("high:", high)
```

## Output Format

Always return exactly these three forecast lines in the final answer, using the
Chronos quantiles:

```text
low: [10th percentile forecast values]
median: [50th percentile forecast values]
high: [90th percentile forecast values]
```

Also include a brief warning when applicable:

- If fewer than 10 history points were provided
- If the model is being downloaded for the first run
- If execution is running on CPU instead of CUDA

## Procedure

Follow this sequence:

1. Parse the user's historical values, horizon, and frequency.
2. Verify the data is numeric and ordered oldest first.
3. Warn if fewer than 10 historical values are available.
4. Install dependencies with `pip install "chronos-forecasting>=2.0" torch` if needed.
5. Run the forecast in Python using `execute_code` or terminal.
6. Extract the three quantile series.
7. Respond with the three required forecast lines: `low`, `median`, `high`.

## Frequency Handling

Accept only these frequency codes:

- `D` for daily
- `H` for hourly
- `W` for weekly
- `M` for monthly

Chronos-2 can forecast from the numeric context alone. The frequency code is
still important to confirm the user's intended cadence and to describe the
forecast horizon correctly in the response.

## Response Guidelines

- Keep the output concrete and numeric.
- Preserve the user's original ordering convention: history is oldest first.
- Do not omit the uncertainty bands.
- Never return only a single best guess; always include `low`, `median`, and `high`.
- If the user has not supplied enough information, ask for the missing history,
  forecast horizon, or frequency before running the model.
