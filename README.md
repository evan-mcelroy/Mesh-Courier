# Mesh Courier

A Python application for transferring files over Meshtastic radio networks. This application provides a user-friendly interface for sending and receiving files through Meshtastic devices, with support for compression.

<img> src=/screenshots/img1 <img>

## Features

- **File Transfer**: Send and receive files over Meshtastic radio networks
- **Compression Support**: Multiple compression options (ZIP, GZIP, LZMA)
- **Reliable Transfer**: Chunked file transfer with ACK-based reliability
- **User Interface**: Clean and intuitive GUI for easy operation
- **Connection Management**: Easy device connection and status monitoring
- **Node Information**: Display of connected node details
- **Transfer Settings**: Configurable retry attempts and wait times

## Supported File Types

- Text files (*.txt)
- CSV files (*.csv)
- JSON files (*.json)
- Archive files (*.zip, *.7z, *.gz, *.lzma, *.xz)

## Requirements

- Python 3.6 or higher
- Meshtastic device
- Required Python packages (see requirements.txt)

## Installation

1. Clone this repository or download the source code
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Connect your Meshtastic device to your computer
2. Run the application:
   ```bash
   python main.py
   ```
3. Select your device from the dropdown menu
4. Click "Connect" to establish connection
5. Click "Select File" to choose a file to send
6. Configure compression settings if desired
7. Click "Send File" to start the transfer

## Transfer Settings

- **Max Attempts**: Number of retry attempts for failed chunks
- **Wait Time**: Time to wait for ACK before retrying (in seconds)
- **Compression**: Choose between different compression methods or none

## Error Handling

The application includes comprehensive error handling for:
- Connection issues
- File access problems
- Transfer failures
- Invalid file types
- Compression/decompression errors

## Troubleshooting

1. **Connection Issues**:
   - Ensure your Meshtastic device is properly connected
   - Check if the correct port is selected
   - Verify device compatibility

2. **Transfer Failures**:
   - Check if the file type is supported
   - Verify file permissions
   - Ensure sufficient memory for file size

3. **Compression Issues**:
   - Try different compression methods
   - Check if the file is already compressed
   - Verify available memory for compression

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the GPL-3.0 license - see the LICENSE file for details.

## Acknowledgments

- Meshtastic project for the underlying radio communication
- Python community for the excellent libraries used in this project 
