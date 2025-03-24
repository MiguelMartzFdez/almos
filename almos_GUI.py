import tkinter as tk
from tkinter import filedialog, messagebox, ttk, PhotoImage
import os
import subprocess
import pandas as pd
from PIL import ImageTk, Image
from pathlib import Path
from pkg_resources import resource_filename
import threading

class ALMOSApp(tk.Tk):
    def __init__(self):
        super().__init__()

        # Create scrollable frame
        self.title("ALMOS")
        self.geometry("625x800")  # Initial window size

        # Main frame and canvas for scrolling
        main_frame = tk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=1)

        canvas = tk.Canvas(main_frame)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)

        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        # Create a frame inside the canvas for the content
        self.scrollable_frame = tk.Frame(canvas)
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

        # Add logo with size limitation
        path_logo = Path(__file__).parent / "icons" / "almos_logo.png"
        resized_image = Image.open(path_logo)
        almos_logo = ImageTk.PhotoImage(resized_image)

        my_logo = tk.Label(self.scrollable_frame, image=almos_logo)
        my_logo.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        my_logo.image = almos_logo

        # Define Terminal Output FIRST
        self.terminal_output = tk.Text(self.scrollable_frame, height=15, width=80, bg="black", fg="white", font=("Courier", 10))
        self.terminal_output.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Define Progress Bar BEFORE passing it
        self.progress = ttk.Progressbar(self.scrollable_frame, orient="horizontal", length=300, mode="indeterminate")
        self.progress.pack(pady=10)

        # Initialize notebook for tabs
        self.tab_control = ttk.Notebook(self.scrollable_frame)

        # Pass 'self.progress' and 'self.terminal_output' AFTER defining them
        self.clustering_tab = ClusteringTab(self.tab_control, self.progress, self.terminal_output)
        self.active_learning_tab = ActiveLearningTab(self.tab_control, self.progress, self.terminal_output)

        # Add tabs to notebook
        self.tab_control.add(self.clustering_tab, text="Clustering")
        self.tab_control.add(self.active_learning_tab, text="Active Learning")

        # Pack the notebook
        self.tab_control.pack(expand=1, fill="both")


class ClusteringTab(tk.Frame):
    def __init__(self, master, progress_bar, terminal_output):
        super().__init__(master)
        self.terminal_output = terminal_output  
        self.progress = progress_bar
        self.file_path = ""
        self.all_columns = []
        
        # Title
        tk.Label(self, text="Clustering", font=("Helvetica", 18, "bold")).pack(pady=10)
        
        # Select CSV File
        self.label = tk.Label(self, text="Select CSV File:")
        self.label.pack(pady=10)
        self.file_button = tk.Button(self, text="Select file", command=self.select_file)
        self.file_button.pack(pady=10)
        
        # Number of Clusters
        self.n_clusters_label = tk.Label(self, text="Number of Clusters:")
        self.n_clusters_label.pack(pady=5)
        self.n_clusters_entry = tk.Entry(self)
        self.n_clusters_entry.pack(pady=5)
        
        # AQME Workflow
        self.aqme_label = tk.Label(self, text="Enable AQME Workflow:")
        self.aqme_label.pack(pady=5)
        self.aqme_var = tk.BooleanVar()
        self.aqme_checkbox = tk.Checkbutton(self, variable=self.aqme_var)
        self.aqme_checkbox.pack(pady=5)

        # Dropdown for selecting name column
        self.name_label = tk.Label(self, text="Select Name Column:")
        self.name_label.pack(pady=5)
        self.name_options = tk.StringVar()
        self.name_dropdown = ttk.Combobox(self, textvariable=self.name_options, state="readonly")
        self.name_dropdown.pack(pady=5)

        # Dropdown for selecting Target Column (optional)
        self.y_label = tk.Label(self, text="Select Target Column (optional):")
        self.y_label.pack(pady=5)
        self.y_options = tk.StringVar()
        self.y_dropdown = ttk.Combobox(self, textvariable=self.y_options, state="readonly")
        self.y_dropdown.pack(pady=5)

        # Listbox for selecting columns to ignore
        self.ignore_label = tk.Label(self, text="Select Columns to Ignore:")
        self.ignore_label.pack(pady=5)
        self.ignore_listbox = tk.Listbox(self, selectmode=tk.MULTIPLE, height=5, width=40)
        self.ignore_listbox.pack(pady=5)

        # Store reference to terminal output
        self.terminal_output.pack(pady=10, fill=tk.BOTH, expand=True)
        
        # Run Button
        self.run_button = tk.Button(self, text="Run Clustering", command=self.run_clustering)
        self.run_button.pack(pady=20)

    def select_file(self):
        self.file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if not self.file_path:
            return  # If no file is selected, exit the function

        self.label.config(text=f"Selected file: {self.file_path}")

        # Read the CSV file
        df = pd.read_csv(self.file_path)
        self.all_columns = list(df.columns)

        # Update the dropdowns for name and target selection
        self.name_dropdown["values"] = ["None"] + self.all_columns
        self.y_dropdown["values"] = ["None"] + self.all_columns

        # Reset selections
        self.name_options.set("None")
        self.y_options.set("None")

        # Update the ignore listbox
        self.ignore_listbox.delete(0, "end")
        for column in self.all_columns:
            self.ignore_listbox.insert("end", column)

    def run_clustering(self):
        if not self.file_path or not self.n_clusters_entry.get():
            messagebox.showwarning("WARNING!", "Please select a CSV file and specify the number of clusters.")
            return
        
        # Start the progress bar
        self.progress.start(10)  # Move every 10ms

        # Retrieve values
        csv_name = self.file_path
        n_clusters = self.n_clusters_entry.get()
        descp_level = 'interpret'
        aqme_workflow = self.aqme_var.get()  # Check if AQME workflow is enabled
        name = self.name_options.get()
        y = self.y_options.get()

        ignore_columns = [self.ignore_listbox.get(i) for i in self.ignore_listbox.curselection()]
        ignore_value = ",".join(ignore_columns)

        # Build the command as a string
        command = f'python -m almos --cluster --csv_name "{csv_name}" --n_clusters "{n_clusters}"'

        # Add AQME workflow if enabled
        if aqme_workflow:
            command += f' --aqme_workflow --descp_level "{descp_level}"'

        # Add name column if provided
        if name:
            command += f' --name "{name}"'

        # Add target column (y) only if selected
        if y != "None":
            command += f' --y "{y}"'

        # Add ignored columns if any
        if ignore_value:
            command += f' --ignore "[{ignore_value}]"'

        # Run the command in a separate thread
        threading.Thread(target=self.execute_command, args=(command,)).start()

        
    def execute_command(self, command):
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)

            # Display output in real-time
            for line in process.stdout:
                self.terminal_output.insert(tk.END, line)
                self.terminal_output.see(tk.END)  # Auto-scroll to the latest output

            # Display errors if any
            stderr = process.stderr.read()
            if stderr:
                self.terminal_output.insert(tk.END, f"\nERROR:\n{stderr}\n")
                self.terminal_output.see(tk.END)

            # Check if the process completed successfully
            process.wait()
            self.progress.stop()

            if process.returncode == 0:
                self.terminal_output.insert(tk.END, "\nProcess completed successfully!\n")
            else:
                self.terminal_output.insert(tk.END, "\nProcess failed.\n")

        except Exception as e:
            self.terminal_output.insert(tk.END, f"\nException occurred: {e}\n")
            self.progress.stop()



class ActiveLearningTab(tk.Frame):
    def __init__(self, master, progress_bar, terminal_output):

        super().__init__(master)
        self.terminal_output = terminal_output  
        self.progress = progress_bar
        self.file_path = ""
        self.all_columns = []
        
        # Title
        tk.Label(self, text="Active Learning", font=("Helvetica", 18, "bold")).pack(pady=10)
        
        # Select CSV File
        self.label = tk.Label(self, text="Select CSV File:")
        self.label.pack(pady=10)
        self.file_button = tk.Button(self, text="Select file", command=self.select_file)
        self.file_button.pack(pady=10)
        
        # Dropdown for selecting target column
        self.y_label = tk.Label(self, text="Select Target Column:")
        self.y_label.pack(pady=5)
        self.y_options = tk.StringVar()
        self.y_dropdown = ttk.Combobox(self, textvariable=self.y_options, state="readonly")
        self.y_dropdown.pack(pady=5)

        # Dropdown for selecting name column
        self.name_label = tk.Label(self, text="Select Name Column:")
        self.name_label.pack(pady=5)
        self.name_options = tk.StringVar()
        self.name_dropdown = ttk.Combobox(self, textvariable=self.name_options, state="readonly")
        self.name_dropdown.pack(pady=5)
        
        # Listbox for selecting columns to ignore
        self.ignore_label = tk.Label(self, text="Select Columns to Ignore:")
        self.ignore_label.pack(pady=5)
        self.ignore_listbox = tk.Listbox(self, selectmode=tk.MULTIPLE, height=5, width=40)
        self.ignore_listbox.pack(pady=5)
        
        # Number of Points
        self.n_points_label = tk.Label(self, text="Number of Points (format: 'explore:exploit'):")
        self.n_points_label.pack(pady=5)
        self.n_points_entry = tk.Entry(self)
        self.n_points_entry.pack(pady=5)

        # Store reference to terminal output
        self.terminal_output.pack(pady=10, fill=tk.BOTH, expand=True)

        # Run Button
        self.run_button = tk.Button(self, text="Run Active Learning", command=self.run_active_learning)
        self.run_button.pack(pady=20)
        
    def select_file(self):
        self.file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        
        if not self.file_path:
            return  # Exit if no file is selected

        self.label.config(text=f"Selected file: {self.file_path}")

        # Read the CSV file and extract column names
        df = pd.read_csv(self.file_path)
        self.all_columns = list(df.columns)

        # Update combobox options for name and target selection
        for dropdown, options in [(self.name_dropdown, self.name_options), (self.y_dropdown, self.y_options)]:
            dropdown["values"] = ["None"] + self.all_columns  # Update available choices
            options.set("None")  # Reset selection to "None"

        # Update listbox for ignore selection
        self.ignore_listbox.delete(0, "end")
        for column in self.all_columns:
            self.ignore_listbox.insert("end", column)


    def run_active_learning(self):
        if not self.file_path or not self.n_points_entry.get() or not self.name_options.get():
            messagebox.showwarning("WARNING!", "Please select a CSV file, name column, and specify the number of points.")
            return
        
        # Start the progress bar
        self.progress.start(10)  # Move every 10ms

        # Retrieve values
        n_points = self.n_points_entry.get()
        y_column = self.y_options.get()
        name_column = self.name_options.get()
        ignore_columns = [self.ignore_listbox.get(i) for i in self.ignore_listbox.curselection()]
        ignore_value = ",".join(ignore_columns)

        # Build the command in the desired format
        command = f'python -m almos --al --csv_name "{self.file_path}" --name "{name_column}" --n_points "{n_points}"'

        # Add --y if a valid target column is selected (optional)
        if y_column != "None":
            command += f' --y "{y_column}"'

        # Add --ignore if there are columns to ignore
        if ignore_value:
            command += f' --ignore "[{ignore_value}]"'

        # Run the command using a separate thread
        threading.Thread(target=self.execute_command, args=(command,)).start()


    def execute_command(self, command):
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)

            # Display output in real-time
            for line in process.stdout:
                self.terminal_output.insert(tk.END, line)
                self.terminal_output.see(tk.END)  # Auto-scroll to the latest output

            # Display errors if any
            stderr = process.stderr.read()
            if stderr:
                self.terminal_output.insert(tk.END, f"\nERROR:\n{stderr}\n")
                self.terminal_output.see(tk.END)

            # Check if the process completed successfully
            process.wait()
            self.progress.stop()

            if process.returncode == 0:
                self.terminal_output.insert(tk.END, "\nProcess completed successfully!\n")
            else:
                self.terminal_output.insert(tk.END, "\nProcess failed.\n")

        except Exception as e:
            self.terminal_output.insert(tk.END, f"\nException occurred: {e}\n")
            self.progress.stop()


if __name__ == "__main__":
    app = ALMOSApp()
    app.mainloop()