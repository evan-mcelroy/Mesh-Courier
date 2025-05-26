import base64
import os
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import serial.tools.list_ports
import io
import zipfile
import gzip
import lzma
from meshtastic.serial_interface import SerialInterface
from pubsub import pub

CHUNK_SIZE = 200
MESSAGE_PREFIX = "MYAPP_FILE_TRANSFER:"
current_iface = None
receiver_chunks = {}
receiver_metadata = {}
ack_event = threading.Event()

WAIT_TIME = 15
MAX_ATTEMPTS = 3

COMPRESSION_NONE = "none"
COMPRESSION_ZIP = "zip"
COMPRESSION_GZIP = "gzip"
COMPRESSION_LZMA = "lzma"

compression_enabled = False
compression_method = COMPRESSION_NONE

selected_filepath = None
original_size = 0
compressed_size = 0

def list_serial_ports():
    try:
        ports = [port.device for port in serial.tools.list_ports.comports()]
        return ports if ports else ["No devices found"]
    except Exception as e:
        print(f"[!] Error listing ports: {e}")
        return ["Error listing ports"]

def refresh_ports(dropdown_var, status_label, node_info_label):
    ports = list_serial_ports()
    if ports and ports[0] != "No devices found" and ports[0] != "Error listing ports":
        dropdown_var.set(ports[0])
        status_label.config(text="🔌 Ready to connect", foreground="#007AFF")
    else:
        dropdown_var.set(ports[0])
        status_label.config(text="🔌 No devices available", foreground="red")
    node_info_label.config(text="No node information available")

def connect_to_selected_port(port, status_label, node_info_label):
    global current_iface
    if port in ["No devices found", "Error listing ports"]:
        messagebox.showerror("Error", "No valid device selected")
        return
        
    try:
        status_label.config(text="🔄 Connecting...", foreground="#007AFF")
        root.update()
        
        current_iface = SerialInterface(devPath=port)
        pub.subscribe(on_receive, "meshtastic.receive")
        status_label.config(text=f"✅ Connected to {port}", foreground="#34C759")
        
        # Get node information
        node_info = current_iface.getMyNodeInfo()
        if node_info:
            node_info_text = f"Node ID: {node_info.get('user', {}).get('id', 'N/A')}\n"
            node_info_text += f"Long Name: {node_info.get('user', {}).get('longName', 'N/A')}\n"
            node_info_text += f"Short Name: {node_info.get('user', {}).get('shortName', 'N/A')}"
            node_info_label.config(text=node_info_text)
        
        print(f"[✓] Connected to {port}")
    except Exception as e:
        status_label.config(text="❌ Connection failed", foreground="#FF3B30")
        node_info_label.config(text="No node information available")
        messagebox.showerror("Connection Error", f"Failed to connect: {str(e)}")
        print(f"[!] Error: {e}")

def disconnect_device(node_info_label, status_label):
    global current_iface
    if current_iface:
        try:
            pub.unsubscribe(on_receive, "meshtastic.receive")
            current_iface.close()
        except Exception:
            pass
        current_iface = None
        node_info_label.config(text="No node information available")
        status_label.config(text="🔌 Disconnected", foreground="#FF3B30")
        print("[🔌] Disconnected.")

def compress_data(data_bytes: bytes, method: str) -> bytes:
    if method == COMPRESSION_NONE:
        return data_bytes
    elif method == COMPRESSION_ZIP:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
            zipf.writestr("file", data_bytes)
        return buf.getvalue()
    elif method == COMPRESSION_GZIP:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            gz.write(data_bytes)
        return buf.getvalue()
    elif method == COMPRESSION_LZMA:
        return lzma.compress(data_bytes)
    else:
        raise ValueError(f"Unknown compression method: {method}")

def decompress_data(data_bytes: bytes, method: str) -> bytes:
    if method == COMPRESSION_NONE:
        return data_bytes
    elif method == COMPRESSION_ZIP:
        buf = io.BytesIO(data_bytes)
        with zipfile.ZipFile(buf, "r") as zipf:
            return zipf.read("file")
    elif method == COMPRESSION_GZIP:
        buf = io.BytesIO(data_bytes)
        with gzip.GzipFile(fileobj=buf, mode="rb") as gz:
            return gz.read()
    elif method == COMPRESSION_LZMA:
        return lzma.decompress(data_bytes)
    else:
        raise ValueError(f"Unknown compression method: {method}")

def calculate_sizes(filepath, compress, method):
    global original_size, compressed_size
    with open(filepath, 'rb') as f:
        raw_data = f.read()
    original_size = len(raw_data)

    if compress and method != COMPRESSION_NONE:
        compressed = compress_data(raw_data, method)
        compressed_size = len(compressed)
    else:
        compressed_size = original_size

def update_size_labels(orig_label, comp_label):
    global original_size, compressed_size
    orig_label.config(text=f"Original Size: {original_size / 1024:.2f} KB")
    comp_label.config(text=f"Size after Compression: {compressed_size / 1024:.2f} KB")

def chunk_file(filepath):
    with open(filepath, 'rb') as f:
        raw_data = f.read()

    global compression_enabled, compression_method
    if compression_enabled and compression_method != COMPRESSION_NONE:
        compressed = compress_data(raw_data, compression_method)
        data = base64.b64encode(compressed).decode('utf-8')
    else:
        data = base64.b64encode(raw_data).decode('utf-8')

    total_chunks = (len(data) + CHUNK_SIZE - 1) // CHUNK_SIZE
    chunks = [data[i*CHUNK_SIZE:(i+1)*CHUNK_SIZE] for i in range(total_chunks)]
    return chunks, total_chunks

def send_file(filepath):
    global WAIT_TIME, MAX_ATTEMPTS, compression_enabled, compression_method

    if not current_iface:
        messagebox.showerror("Error", "No device connected.")
        return

    filename = os.path.basename(filepath)
    ext = filename.split('.')[-1].lower()
    allowed_exts = ['txt', 'csv', 'json', '7z', 'zip', 'gz', 'lzma', 'xz']
    if ext not in allowed_exts:
        messagebox.showerror("Invalid File", f"Only files with extensions {allowed_exts} are allowed.")
        return

    chunks, total_chunks = chunk_file(filepath)

    compression_flag = compression_method if compression_enabled else COMPRESSION_NONE
    print(f"[+] Sending {filename} ({'compressed' if compression_enabled else 'uncompressed'}) in {total_chunks} chunks using {compression_flag.upper()}.")

    current_iface.sendText(MESSAGE_PREFIX + f"FILE_START:{filename}:{total_chunks}:{compression_flag}")
    time.sleep(1)

    for i, chunk in enumerate(chunks):
        attempt = 0
        while attempt < MAX_ATTEMPTS:
            ack_event.clear()
            current_iface.sendText(MESSAGE_PREFIX + f"CHUNK:{i}:{chunk}")
            print(f"[>] Sent chunk {i}, attempt {attempt + 1}")

            if ack_event.wait(timeout=WAIT_TIME):
                print(f"[✓] ACK received for chunk {i}")
                break
            else:
                print(f"[!] No ACK for chunk {i}, retrying...")
                attempt += 1

        if attempt == MAX_ATTEMPTS:
            print(f"[✗] Failed to send chunk {i} after {MAX_ATTEMPTS} attempts.")
            messagebox.showerror("Error", f"Failed to send chunk {i}. Transfer aborted.")
            return

    current_iface.sendText(MESSAGE_PREFIX + "FILE_END")
    print("[✓] File sent.")

def on_receive(packet, interface):
    text = packet.get('decoded', {}).get('text', '')
    if not text.startswith(MESSAGE_PREFIX):
        return

    text = text[len(MESSAGE_PREFIX):]

    if text.startswith("ACK:"):
        try:
            ack_idx = int(text.split(":")[1])
            ack_event.set()
            print(f"[⬅️] Received ACK for chunk {ack_idx}")
        except Exception as e:
            print(f"[!] Error parsing ACK: {e}")
        return

    if text.startswith("FILE_START:"):
        try:
            _, fname, total, compression_flag = text.split(":")
            receiver_metadata['filename'] = fname
            receiver_metadata['total'] = int(total)
            receiver_metadata['compression'] = compression_flag
            receiver_chunks.clear()
            print(f"[🛬] Receiving {fname} with {total} chunks... Compression: {compression_flag.upper()}")
        except Exception as e:
            print(f"[!] Error parsing FILE_START: {e}")

    elif text.startswith("CHUNK:"):
        try:
            _, idx, chunk_data = text.split(":", 2)
            idx = int(idx)

            if idx not in receiver_chunks:
                receiver_chunks[idx] = chunk_data
                print(f"[+] Received chunk {idx}")
            else:
                print(f"[=] Duplicate chunk {idx} ignored")

            if current_iface:
                current_iface.sendText(MESSAGE_PREFIX + f"ACK:{idx}")
        except Exception as e:
            print(f"[!] Error parsing chunk: {e}")

    elif text == "FILE_END":
        total = receiver_metadata.get("total", 0)
        if len(receiver_chunks) == total:
            print("[✓] All chunks received. Reassembling...")
            save_received_file()
        else:
            print(f"[!] Missing chunks ({len(receiver_chunks)}/{total}). File incomplete.")

def save_received_file():
    ordered_data = ''.join(receiver_chunks[i] for i in sorted(receiver_chunks))
    compressed_bytes = base64.b64decode(ordered_data)

    fname = receiver_metadata.get("filename", "received_file")
    compression_flag = receiver_metadata.get("compression", COMPRESSION_NONE)

    try:
        if compression_flag != COMPRESSION_NONE:
            print(f"[⚙️] Decompressing received file using {compression_flag.upper()}...")
            data_bytes = decompress_data(compressed_bytes, compression_flag)
        else:
            data_bytes = compressed_bytes
    except Exception as e:
        messagebox.showerror("Error", f"Failed to decompress file: {e}")
        return

    _, ext = os.path.splitext(fname)
    if not ext:
        ext = ""

    save_path = filedialog.asksaveasfilename(
        title="Save Received File",
        initialfile=fname,
        defaultextension=ext,
        filetypes=[(f"{ext.upper()} files", f"*{ext}"), ("All files", "*.*")]
    )
    if save_path:
        with open(save_path, "wb") as f:
            f.write(data_bytes)
        messagebox.showinfo("Success", f"File saved as:\n{save_path}")

def on_select_file(orig_label, comp_label):
    global selected_filepath, compression_enabled, compression_method
    try:
        filepath = filedialog.askopenfilename(
            title="Select File to Send",
            filetypes=[
                ("All files", "*.*"),
                ("Text files", "*.txt"),
                ("CSV files", "*.csv"),
                ("JSON files", "*.json"),
                ("Archive files", "*.zip *.7z *.gz *.lzma *.xz")
            ]
        )
        if filepath:
            # Check if file is accessible
            if not os.access(filepath, os.R_OK):
                messagebox.showerror("Error", "Cannot access the selected file. Please check file permissions.")
                return
                
            selected_filepath = filepath
            calculate_sizes(selected_filepath, compression_enabled, compression_method)
            update_size_labels(orig_label, comp_label)
            
            # Update the send button state
            send_btn.config(state=tk.NORMAL)
    except Exception as e:
        messagebox.showerror("Error", f"Error selecting file: {str(e)}")
        selected_filepath = None
        orig_label.config(text="Original Size: N/A")
        comp_label.config(text="Size after Compression: N/A")
        send_btn.config(state=tk.DISABLED)

def launch_gui():
    global WAIT_TIME, MAX_ATTEMPTS, compression_enabled, compression_method, selected_filepath, root, send_btn

    root = tk.Tk()
    root.title("Mesh Courier")
    root.geometry("600x700")
    root.resizable(False, False)  # Disable window resizing

    # Main container
    main_frame = tk.Frame(root, padx=15, pady=15)
    main_frame.pack(fill=tk.BOTH, expand=True)

    # Title
    title_label = tk.Label(main_frame, text="Mesh Courier", font=('Helvetica', 24, 'bold'))
    title_label.pack(pady=(0, 20))

    # Connection section
    conn_frame = tk.LabelFrame(main_frame, text="Connection", padx=10, pady=10)
    conn_frame.pack(fill=tk.X, pady=(0, 20))

    status = tk.Label(conn_frame, text="Ready to connect")
    status.pack(pady=(0, 10))

    # Port selection
    port_frame = tk.Frame(conn_frame)
    port_frame.pack(fill=tk.X, pady=5)

    ports = list_serial_ports()
    dropdown_var = tk.StringVar(value=ports[0] if ports else "No devices found")

    port_dropdown = ttk.Combobox(port_frame, textvariable=dropdown_var, 
                                values=ports, state="readonly", width=35)
    port_dropdown.pack(side=tk.LEFT, padx=(0, 10))

    refresh_btn = tk.Button(port_frame, text="Refresh",
                          command=lambda: refresh_ports(dropdown_var, status, node_info_label))
    refresh_btn.pack(side=tk.LEFT, padx=5)

    connect_btn = tk.Button(port_frame, text="Connect",
                          command=lambda: connect_to_selected_port(dropdown_var.get(), status, node_info_label))
    connect_btn.pack(side=tk.LEFT, padx=5)

    disconnect_btn = tk.Button(port_frame, text="Disconnect",
                             command=lambda: [disconnect_device(node_info_label, status)])
    disconnect_btn.pack(side=tk.LEFT, padx=5)

    # Node information
    node_frame = tk.LabelFrame(main_frame, text="Node Information", padx=10, pady=10)
    node_frame.pack(fill=tk.X, pady=(0, 20))
    
    node_info_label = tk.Label(node_frame, text="No node information available")
    node_info_label.pack(pady=5)

    # File transfer section
    file_frame = tk.LabelFrame(main_frame, text="File Transfer", padx=10, pady=10)
    file_frame.pack(fill=tk.X, pady=(0, 20))

    # File selection
    select_frame = tk.Frame(file_frame)
    select_frame.pack(fill=tk.X, pady=5)

    # Create labels first
    orig_size_label = tk.Label(select_frame, text="Original Size: N/A")
    comp_size_label = tk.Label(select_frame, text="Size after Compression: N/A")

    select_btn = tk.Button(select_frame, text="Select File",
                         command=lambda: on_select_file(orig_size_label, comp_size_label))
    select_btn.pack(side=tk.LEFT, padx=(0, 15))

    orig_size_label.pack(side=tk.LEFT, padx=5)
    comp_size_label.pack(side=tk.LEFT, padx=5)

    # Settings section
    settings_frame = tk.LabelFrame(main_frame, text="Settings", padx=10, pady=10)
    settings_frame.pack(fill=tk.X, pady=(0, 20))

    # Transmission settings
    trans_frame = tk.LabelFrame(settings_frame, text="Transmission Settings", padx=10, pady=10)
    trans_frame.pack(fill=tk.X, pady=(0, 10))

    tk.Label(trans_frame, text="Max Attempts:").pack(side=tk.LEFT, padx=(0, 5))
    
    attempts_entry = tk.Entry(trans_frame, width=5)
    attempts_entry.insert(0, str(MAX_ATTEMPTS))
    attempts_entry.pack(side=tk.LEFT, padx=(0, 15))

    tk.Label(trans_frame, text="Wait Time (s):").pack(side=tk.LEFT, padx=(0, 5))
    
    wait_entry = tk.Entry(trans_frame, width=5)
    wait_entry.insert(0, str(WAIT_TIME))
    wait_entry.pack(side=tk.LEFT, padx=(0, 15))

    def update_transfer_settings():
        global WAIT_TIME, MAX_ATTEMPTS
        try:
            MAX_ATTEMPTS = int(attempts_entry.get())
            WAIT_TIME = int(wait_entry.get())
            messagebox.showinfo("Success", "Transfer settings updated.")
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numbers.")

    apply_btn = tk.Button(trans_frame, text="Apply Settings",
                        command=update_transfer_settings)
    apply_btn.pack(side=tk.LEFT)

    # Compression options
    comp_frame = tk.LabelFrame(settings_frame, text="Compression Settings", padx=10, pady=10)
    comp_frame.pack(fill=tk.X, pady=(0, 10))

    compress_var = tk.BooleanVar(value=False)
    compress_check = tk.Checkbutton(comp_frame, text="Compress before sending",
                                  variable=compress_var)
    compress_check.pack(side=tk.LEFT, padx=(0, 15))

    compression_types = [COMPRESSION_NONE, COMPRESSION_ZIP, COMPRESSION_GZIP, COMPRESSION_LZMA]
    compression_var = tk.StringVar(value=COMPRESSION_NONE)
    comp_dropdown = ttk.Combobox(comp_frame, textvariable=compression_var,
                                values=compression_types, state="readonly", width=15)
    comp_dropdown.pack(side=tk.LEFT)

    # Send button
    send_btn = tk.Button(main_frame, text="Send File",
                       command=lambda: send_file(selected_filepath),
                       state=tk.DISABLED)  # Initially disabled
    send_btn.pack(pady=15)

    def update_compression_settings(*args):
        global compression_enabled, compression_method
        compression_enabled = compress_var.get()
        compression_method = compression_var.get()

        if selected_filepath:
            calculate_sizes(selected_filepath, compression_enabled, compression_method)
            update_size_labels(orig_size_label, comp_size_label)

    compress_var.trace_add("write", update_compression_settings)
    compression_var.trace_add("write", update_compression_settings)

    # Initial port refresh
    refresh_ports(dropdown_var, status, node_info_label)

    root.mainloop()

if __name__ == "__main__":
    launch_gui()
