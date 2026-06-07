# generate-xml.ps1
# Generates ipccacronyms.xml from ipccacronyms_normalised.csv, enriched with
# per-description report-source attribution derived from ipccacronyms.csv.
# The output validates against ipccacronyms.dtd in the same directory.

$scriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$origPath   = Join-Path $scriptDir "ipccacronyms.csv"
$normPath   = Join-Path $scriptDir "ipccacronyms_normalised.csv"
$xmlPath    = Join-Path $scriptDir "ipccacronyms.xml"
$dtdSysId   = "ipccacronyms.dtd"   # relative SYSTEM identifier used in DOCTYPE

# --- Load data ---------------------------------------------------------------

$origRows = Import-Csv $origPath -Encoding UTF8
$normRows = Import-Csv $normPath -Encoding UTF8

# Build lookup: Acronym -> { Description -> [Reports] }
# Used to annotate each <description> with its source reports.
# Inner dictionary uses Ordinal (case-sensitive) comparison so description
# variants that differ only in capitalisation are kept as distinct entries.
$lookup = @{}
foreach ($row in $origRows) {
    $acr  = $row.Acronym
    $desc = $row.Description
    $rep  = $row.Report

    if (-not $lookup.ContainsKey($acr)) {
        $lookup[$acr] = [System.Collections.Generic.Dictionary[string, object]]::new(
            [System.StringComparer]::Ordinal
        )
    }
    if (-not $lookup[$acr].ContainsKey($desc)) {
        $lookup[$acr][$desc] = [System.Collections.Generic.List[string]]::new()
    }
    if (-not $lookup[$acr][$desc].Contains($rep)) {
        $lookup[$acr][$desc].Add($rep)
    }
}

# --- Build XML ---------------------------------------------------------------

$settings = New-Object System.Xml.XmlWriterSettings
$settings.Encoding   = New-Object System.Text.UTF8Encoding($false)  # UTF-8, no BOM
$settings.Indent     = $true
$settings.IndentChars = "  "

$writer = [System.Xml.XmlWriter]::Create($xmlPath, $settings)

$writer.WriteStartDocument()
$writer.WriteDocType("ipcc-acronyms", $null, $dtdSysId, $null)
$writer.WriteStartElement("ipcc-acronyms")

$index = 1
foreach ($row in $normRows) {

    $writer.WriteStartElement("acronym")
    $writer.WriteAttributeString("id", ("A" + $index.ToString("D4")))

    # <code>
    $writer.WriteElementString("code", $row.Acronym)

    # <descriptions>
    # Descriptions that are identical except for capitalisation are merged into
    # a single element, keeping the variant with the most uppercase letters
    # (i.e. title/sentence case preferred over all-lowercase).
    $writer.WriteStartElement("descriptions")
    $descs = $row.Description -split "; " | Where-Object { $_ -ne "" }

    # Pass 1: determine the best-cased canonical string per case-insensitive group.
    $descCanonical = @{}   # lowercase key -> canonical (best-cased) string
    foreach ($d in $descs) {
        $key = $d.ToLowerInvariant()
        if (-not $descCanonical.ContainsKey($key)) {
            $descCanonical[$key] = $d
        } else {
            $existingUpper = ($descCanonical[$key].ToCharArray() | Where-Object { [char]::IsUpper($_) }).Count
            $thisUpper     = ($d.ToCharArray()                   | Where-Object { [char]::IsUpper($_) }).Count
            if ($thisUpper -gt $existingUpper) { $descCanonical[$key] = $d }
        }
    }

    # Pass 2: write one <description> per case-insensitive group, preserving
    # original order and merging source reports from all case-variants.
    $written = [System.Collections.Generic.HashSet[string]]::new()
    foreach ($d in $descs) {
        $key = $d.ToLowerInvariant()
        if (-not $written.Contains($key)) {
            $null = $written.Add($key)
            $canonical = $descCanonical[$key]

            # Accumulate sources from every case-variant of this description.
            $allSources = [System.Collections.Generic.List[string]]::new()
            foreach ($variant in $descs) {
                if ($variant.ToLowerInvariant() -eq $key) {
                    if ($lookup.ContainsKey($row.Acronym) -and $lookup[$row.Acronym].ContainsKey($variant)) {
                        foreach ($s in $lookup[$row.Acronym][$variant]) {
                            if (-not $allSources.Contains($s)) { $allSources.Add($s) }
                        }
                    }
                }
            }

            $writer.WriteStartElement("description")
            if ($allSources.Count -gt 0) {
                $writer.WriteAttributeString("source", ($allSources -join "; "))
            }
            $writer.WriteString($canonical)
            $writer.WriteEndElement()   # </description>
        }
    }
    $writer.WriteEndElement()       # </descriptions>

    # <reports>
    $writer.WriteStartElement("reports")
    $reps = $row.Report -split "; " | Where-Object { $_ -ne "" }
    foreach ($r in $reps) {
        $writer.WriteElementString("report", $r)
    }
    $writer.WriteEndElement()       # </reports>

    $writer.WriteEndElement()       # </acronym>
    $index++
}

$writer.WriteEndElement()           # </ipcc-acronyms>
$writer.WriteEndDocument()
$writer.Flush()
$writer.Close()

Write-Host "Generated: $xmlPath  ($($normRows.Count) acronyms)"

# --- Validate against DTD ----------------------------------------------------

Write-Host "Validating against $dtdSysId ..."

$readerSettings = New-Object System.Xml.XmlReaderSettings
$readerSettings.DtdProcessing  = [System.Xml.DtdProcessing]::Parse
$readerSettings.ValidationType = [System.Xml.ValidationType]::DTD

$validationErrors = [System.Collections.Generic.List[string]]::new()
$handler = [System.Xml.Schema.ValidationEventHandler]{
    param($sender, $e)
    $validationErrors.Add($e.Message)
}
$readerSettings.add_ValidationEventHandler($handler)

try {
    $reader = [System.Xml.XmlReader]::Create($xmlPath, $readerSettings)
    while ($reader.Read()) {}
    $reader.Close()
} catch {
    Write-Warning "XML parse error: $($_.Exception.Message)"
}

if ($validationErrors.Count -eq 0) {
    Write-Host "Validation PASSED - XML is valid against the DTD."
} else {
    Write-Warning "$($validationErrors.Count) validation error(s):"
    $validationErrors | ForEach-Object { Write-Warning "  $_" }
}
