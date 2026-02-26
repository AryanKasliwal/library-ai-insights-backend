#!/bin/bash

echo "╔════════════════════════════════════════╗"
echo "║  RECOMMENDATION BUILD STATUS CHECK     ║"
echo "╚════════════════════════════════════════╝"
echo ""

# Check if process is running
PID=$(pgrep -f "build_recommendation_index.py")

if [ -z "$PID" ]; then
    echo "❌ Process NOT running"
    
    # Check if output file exists
    if [ -f "app/services/book_recommendations.json" ]; then
        echo "✅ Output file created successfully!"
        ls -lh app/services/book_recommendations.json
        echo ""
        echo "Build completed. Ready to test API endpoints."
    else
        echo "⚠️  Output file not found. Build may have failed."
    fi
else
    echo "✅ Process is RUNNING (PID: $PID)"
    echo ""
    
    # Get process stats
    STATS=$(ps -p $PID -o %cpu=,%mem=,etime= | awk '{print "CPU: "$1"% | Memory: "$2"% | Runtime: "$3}')
    echo "$STATS"
    echo ""
    
    # Check current output file size
    if [ -f "app/services/book_recommendations.json" ]; then
        SIZE=$(du -h app/services/book_recommendations.json | cut -f1)
        LINES=$(wc -l < app/services/book_recommendations.json)
        echo "📄 Output file: $SIZE ($LINES lines)"
    else
        echo "📄 Output file: Not yet created (still computing...)"
    fi
    
    echo ""
    echo "Estimated completion: 45-60 minutes from start"
    echo "Total books: 111,827"
    echo "Pair comparisons: 12.5 billion"
fi

echo ""