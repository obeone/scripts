# syntax=docker/dockerfile:1

# ==============================================================================
# Build Stage: Compile Python wheels for the application.
#
# This stage is responsible for creating Python wheel files for the application
# and its dependencies. This allows for a clean and minimal final image, as
# build-time dependencies are not included in the runtime stage.
# ==============================================================================
FROM python:3.13-slim AS builder

# --- Environment Configuration ---
# PYTHONDONTWRITEBYTECODE=1: Prevents Python from writing .pyc files.
# PYTHONUNBUFFERED=1: Ensures that Python output is sent straight to the terminal.
# LANG=C.UTF-8: Sets the default locale to prevent encoding issues.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8

# --- Source Code and Working Directory ---
WORKDIR /src
# Copy the application source code into the container.
# The .dockerignore file should be used to exclude unnecessary files.
COPY --link . .

# --- Dependency Installation ---
# Build wheel files for the application and its dependencies.
# This uses a persistent cache to speed up subsequent builds.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --wheel-dir /wheels .

# ==============================================================================
# Runtime Stage: Create the final, lightweight application image.
#
# This stage builds the final image that will be used to run the application.
# It starts from a clean Python base image and installs the pre-built wheels
# from the builder stage, ensuring a small and secure final image.
# ==============================================================================
FROM python:3.13-slim

# --- Environment Configuration ---
# Apply the same sane runtime defaults for consistency.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8

# --- Security: Non-Root User ---
# Create a non-root user and group to run the application for better security.
RUN addgroup --system app && adduser --system --ingroup app app
WORKDIR /home/app

# --- Application Installation ---
# Copy the pre-built wheels from the builder stage.
COPY --from=builder /wheels /wheels
# Install the application from the local wheel files without network access.
# The pip cache is mounted to speed up installation if possible.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-index --find-links=/wheels /wheels/*.whl && \
    rm -rf /wheels

# --- Runtime Execution ---
# Switch to the non-root user.
USER app
# Set the entrypoint to the console script defined in pyproject.toml.
ENTRYPOINT ["openai-usage"]