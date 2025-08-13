# 🚀 transfer.sh

A powerful and feature-rich command-line tool to interact with the [Transfer.sh](https://transfer.sh) service for seamless file sharing.

## 📜 Description

This script provides a convenient and robust way to **upload**, **download**, **delete**, and get **information** about files hosted on any Transfer.sh instance. It's designed for ease of use and flexibility, supporting advanced features like client-side encryption, download limits, and file expiration.

## ✨ Features

- 📤 **Send** files and directories with ease.
- 📥 **Receive** files directly to your machine.
- 🗑️ **Delete** files from the server when they are no longer needed.
- ℹ️ Get **information** about a shared file (size, expiration, etc.).
- 🔒 Client-side **encryption/decryption** (AES-256-CBC) for maximum privacy.
- 📦 Automatic **zipping** of multiple files or directories before upload.
- ⚙️ Set **maximum downloads** and **expiration days** for your shares.
- 📊 **Progress bars** for uploads and downloads powered by `pv`.
- 🌐 Support for **custom Transfer.sh instances**.
- 🔐 **Basic Authentication** support for private instances.
- 🎨 Colorful and informative logging.

## ✅ Requirements

Make sure you have these tools installed on your system:

- `curl`
- `openssl`
- `zip`
- `pv`

## 🛠️ Installation

1. **Clone the repository or download the script:**

    ```bash
    # Using git
    git clone https://github.com/obeone/scripts.git
    cd scripts/transfer.sh

    # Or just download the script
    curl -o transfer.sh https://raw.githubusercontent.com/obeone/scripts/main/transfer.sh/transfer.sh
    ```

2. **Make the script executable:**

    ```bash
    chmod +x transfer.sh
    ```

3. **(Optional) Move it to your PATH:**
    For easy access from anywhere, move the script to a directory in your system's `PATH`.

    ```bash
    sudo mv transfer.sh /usr/local/bin/
    ```

## Usage

The script is command-based, similar to `git` or `docker`.

```bash
./transfer.sh [GLOBAL OPTIONS] <command> [COMMAND OPTIONS]
```

### 🌍 Global Options

- `--log-level <level>`: Set the logging level (`ERROR`, `WARN`, `INFO`, `DEBUG`). Default: `INFO`.
- `--tmp-dir <directory>`: Set a custom temporary directory for intermediate files.

---

### Commands

#### 📤 `send`

Uploads one or more files or directories. If you provide multiple items or a single directory, they will be automatically zipped.

```bash
./transfer.sh send [OPTIONS] <file|directory>...
```

**Options:**

- `-d, --max-downloads <value>`: Set the maximum number of downloads.
- `-D, --max-days <value>`: Set the maximum number of days the file is stored.
- `-k, --key <value>`: Encryption key for your file.
- `-u, --user <value>`: Username for basic authentication.
- `-p, --password <value>`: Password for basic authentication.
- `-y`: Bypass the confirmation prompt for a faster workflow.
- `-h, --help`: Display the help message for the `send` command.

**Examples:**

```bash
# Upload a single file
./transfer.sh send ./myfile.txt

# Upload and encrypt a file with a secret key
./transfer.sh send --key "mySuperSecretKey123" ./my-document.pdf

# Upload and zip a folder and another file
./transfer.sh send ./my_project_folder/ ./notes.txt

# Upload a file with a 5-download limit, expiring in 3 days
./transfer.sh send -d 5 -D 3 ./release.zip
```

#### 📥 `receive`

Downloads a file from a Transfer.sh URL.

```bash
./transfer.sh receive [OPTIONS] <URL> [destination]
```

**Options:**

- `-k, --key <value>`: Decryption key if the file is encrypted.
- `-u, --unzip`: Offer to unzip the file after download if it's a `.zip` or `.tar.gz` archive.
- `-h, --help`: Display the help message for the `receive` command.

**Examples:**

```bash
# Download a file to the current directory
./transfer.sh receive https://transfer.obeone.cloud/example/myfile.txt

# Download and decrypt a file
./transfer.sh receive --key "mySuperSecretKey123" https://transfer.obeone.cloud/example/myfile.txt.enc

# Download an archive and get prompted to unzip it
./transfer.sh receive -u https://transfer.obeone.cloud/example/archive.zip

# Download a file to a specific path
./transfer.sh receive https://transfer.obeone.cloud/example/image.jpg /home/user/images/
```

#### 🗑️ `delete`

Deletes a file from the server using the delete URL provided after uploading.

```bash
./transfer.sh delete <X-URL-Delete>
```

**Example:**

```bash
./transfer.sh delete https://transfer.obeone.cloud/example/myfile.txt/L2s3j...
```

#### ℹ️ `info`

Retrieves and displays metadata about a file.

```bash
./transfer.sh info <URL>
```

**Example:**

```bash
./transfer.sh info https://transfer.obeone.cloud/example/myfile.txt
```

---

## ⚙️ Environment Variables

Configure the script's default behavior by setting these environment variables:

- `TRANSFERSH_URL`: The URL of the Transfer.sh service. (Default: `https://transfer.obeone.cloud`)
- `TRANSFERSH_MAX_DAYS`: Default maximum number of days for storage.
- `TRANSFERSH_MAX_DOWNLOADS`: Default maximum number of downloads.
- `TRANSFERSH_ENCRYPTION_KEY`: Default encryption/decryption key.
- `LOG_LEVEL`: Default log level (`ERROR`, `WARN`, `INFO`, `DEBUG`). (Default: `INFO`)
- `AUTH_USER`: Username for basic authentication.
- `AUTH_PASS`: Password for basic authentication.
- `TMPDIR`: Path to the temporary directory.

## 👨‍💻 Author

- **Grégoire Compagnon** (obeone) - [obeone@obeone.org](mailto:obeone@obeone.org)

## 📄 License

This project is licensed under the MIT License.
