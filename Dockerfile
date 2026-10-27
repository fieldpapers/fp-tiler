FROM public.ecr.aws/lambda/python:3.13

# The rasterio wheel expects these from the system.
RUN dnf install -y expat libstdc++ && dnf clean all

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR ${LAMBDA_TASK_ROOT}

COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project -o requirements.txt \
  && uv pip install --no-cache --target . -r requirements.txt

COPY src/fptiler ./fptiler

CMD ["fptiler.app.handler"]
